import os
import time
import json
import re
from typing import TypedDict, Optional
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.core.database import async_session
from app.models.pesticide import PesticideProduct
from sqlalchemy import select

load_dotenv()

class DiagnosisState(TypedDict):
    pest: str
    crop: str
    region: str
    weather_data: Optional[str]
    ncpms_data: Optional[str]
    pesticide_data: Optional[str]
    analysis_result: Optional[dict]

# -----------------
# Caching In-Memory (NCPMS & Weather)
# -----------------
ncpms_cache = {}   # key: (crop, pest) -> (timestamp_sec, data_str)
weather_cache = {} # key: region -> (timestamp_sec, data_str)

NCPMS_CACHE_TTL = 30 * 24 * 3600  # 30일
WEATHER_CACHE_TTL = 3 * 3600      # 3시간

import math
import urllib.parse

def map_to_grid(lat, lon):
    RE = 6371.00877 # 지구 반경(km)
    GRID = 5.0      # 격자 간격(km)
    SLAT1 = 30.0    # 투영 위도1(degree)
    SLAT2 = 60.0    # 투영 위도2(degree)
    OLON = 126.0    # 기준점 경도(degree)
    OLAT = 38.0     # 기준점 위도(degree)
    XO = 43         # 기준점 X좌표(GRID)
    YO = 136        # 기점 Y좌표(GRID)

    DEGRAD = math.pi / 180.0
    RADDEG = 180.0 / math.pi
    
    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / math.pow(ro, sn)

    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / math.pow(ra, sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    x = math.floor(ra * math.sin(theta) + XO + 0.5)
    y = math.floor(ro - ra * math.cos(theta) + YO + 0.5)
    return str(int(x)), str(int(y))

async def fetch_weather(state: DiagnosisState) -> dict:
    region = state.get("region", "서울") # region fields now acts as full address

    now = time.time()
    if region in weather_cache:
        cached_time, cached_data = weather_cache[region]
        if now - cached_time < WEATHER_CACHE_TTL:
            return {"weather_data": cached_data}
            
    from app.core.config import settings
    api_key = settings.WEATHER_API_KEY
    kakao_key = settings.KAKAO_REST_API_KEY
    if not api_key:
        return {"weather_data": {"status": "에러", "message": "API 키 오류"}}

    import requests
    from datetime import datetime, timedelta
    
    # 1. Kakao API로 주소를 좌표로 변환
    nx, ny = "60", "127" # default fallback (서울)
    try:
        if kakao_key:
            kakao_url = f"https://dapi.kakao.com/v2/local/search/address.json?query={urllib.parse.quote(region)}"
            headers = {"Authorization": f"KakaoAK {kakao_key}"}
            k_resp = requests.get(kakao_url, headers=headers, timeout=5)
            if k_resp.status_code == 200:
                k_data = k_resp.json()
                if k_data.get("documents"):
                    doc = k_data["documents"][0]
                    lat = float(doc["y"])
                    lon = float(doc["x"])
                    nx, ny = map_to_grid(lat, lon)
    except Exception as e:
        print("Kakao API Error:", e)

    # 2. 기상청 단기예보 조회 (약 3일치)
    current_time = datetime.now()
    # 단기예보는 0200, 0500, 0800 등에 발표
    # 일최저/일최고 기온(TMN, TMX)을 포함해 온전한 하루 데이터를 얻기 위해, 
    # 항상 그날의 가장 이른 발표 시각(02:00)이나 전날 23:00 예보를 기준으로 조회하도록 시간 조정
    if current_time.hour < 2 or (current_time.hour == 2 and current_time.minute < 10):
        target = current_time - timedelta(days=1)
        target = target.replace(hour=23, minute=0, second=0)
        base_date = target.strftime("%Y%m%d")
        base_time = "2300"
    else:
        base_date = current_time.strftime("%Y%m%d")
        base_time = "0200"
    
    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    # numOfRows=1000 정도면 02:00 발표 기준 미래 3일치 전체(TMN, TMX 포함) 조회 가능
    params = {
        "serviceKey": api_key, "pageNo": "1", "numOfRows": "1000", "dataType": "JSON", 
        "base_date": base_date, 
            "base_time": base_time, 
            "nx": nx, "ny": ny
        }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            
            # 날짜/시간별로 정리
            forecast_by_date = {}
            for item in items:
                fcst_date = item.get('fcstDate')
                fcst_time = item.get('fcstTime')
                cat = item.get('category')
                val = item.get('fcstValue')
                
                dt_key = f"{fcst_date}_{fcst_time}"
                if dt_key not in forecast_by_date:
                    forecast_by_date[dt_key] = {}
                
                if cat == 'TMP': forecast_by_date[dt_key]['temperature'] = val
                elif cat == 'TMN': forecast_by_date[dt_key]['daily_min_temp'] = val
                elif cat == 'TMX': forecast_by_date[dt_key]['daily_max_temp'] = val
                elif cat == 'POP': forecast_by_date[dt_key]['precipitation_prob'] = val
                elif cat == 'WSD': forecast_by_date[dt_key]['wind_speed'] = val
                elif cat == 'REH': forecast_by_date[dt_key]['humidity'] = val
                elif cat == 'SKY': forecast_by_date[dt_key]['sky'] = val
                elif cat == 'PTY': forecast_by_date[dt_key]['precipitation_type'] = val
            
            # 3일치 요약 생성 (최고/최저 기온, 강수 확률 등 묶기)
            daily_summary = {}
            for dt_key, fcst in forecast_by_date.items():
                d = dt_key.split('_')[0]
                if d not in daily_summary:
                    daily_summary[d] = {"temps": [], "pops": [], "hums": [], "winds": [], "skys": [], "ptys": [], "tmn": None, "tmx": None}

                if 'temperature' in fcst: daily_summary[d]["temps"].append(float(fcst['temperature']))
                if 'precipitation_prob' in fcst: daily_summary[d]["pops"].append(int(fcst['precipitation_prob']))
                if 'wind_speed' in fcst: daily_summary[d]["winds"].append(float(fcst['wind_speed']))
                if 'humidity' in fcst: daily_summary[d]["hums"].append(int(fcst['humidity']))
                if 'daily_min_temp' in fcst: daily_summary[d]["tmn"] = float(fcst['daily_min_temp'].replace('℃', ''))
                if 'daily_max_temp' in fcst: daily_summary[d]["tmx"] = float(fcst['daily_max_temp'].replace('℃', ''))
                if 'sky' in fcst: daily_summary[d]["skys"].append(int(fcst['sky']))
                if 'precipitation_type' in fcst: daily_summary[d]["ptys"].append(int(fcst['precipitation_type']))
            formatted_summary = {}
            for d, vals in daily_summary.items():
                temps = vals["temps"]
                pops = vals["pops"]
                winds = vals["winds"]
                skys = vals["skys"]
                ptys = vals["ptys"]

                # 기상청이 제공하는 공식 일최저(TMN)/일최고(TMX)를 우선 사용하고, 없으면 시간별(TMP) 기온에서 추출
                min_t = vals["tmn"] if vals.get("tmn") is not None else (min(temps) if temps else None)
                max_t = vals["tmx"] if vals.get("tmx") is not None else (max(temps) if temps else None)

                max_pty = max(ptys) if ptys else 0
                max_sky = max(skys) if skys else 1
                condition_text = "☀️ 맑음"
                if max_pty > 0:
                    if max_pty == 3: condition_text = "❄️ 눈"
                    else: condition_text = "🌧️ 비"
                else:
                    if max_sky >= 4: condition_text = "☁️ 흐림"
                    elif max_sky >= 3: condition_text = "⛅ 구름많음"

                if min_t is not None and max_t is not None:
                    formatted_summary[d] = {
                        "min_temp": min_t,
                        "max_temp": max_t,
                        "max_precip_prob": max(pops) if pops else 0,
                        "max_wind_speed": max(winds) if winds else 0.0,
                        "condition": condition_text
                    }
                    
            w_dict = {"daily_forecast": formatted_summary, "query_address": region, "grid": f"{nx},{ny}"}
            weather_cache[region] = (now, w_dict)
            return {"weather_data": w_dict}
            
        return {"weather_data": {"status": "에러", "message": "기상청 서버 응답 오류"}}
    except Exception as e:
        return {"weather_data": {"status": "에러", "message": str(e)}}

async def fetch_ncpms(state: DiagnosisState) -> dict:
    pest = state.get("pest", "알 수 없음")
    crop = state.get("crop", "알 수 없음")
    
    if not pest or pest == "알수없음": 
        return {"ncpms_data": "[정보 누락] 해충명이 명확하지 않아 지침을 조회할 수 없습니다."}
        
    synonyms = {
        "비단노린재": "홍비단노린재",
        "큰28점박이무당벌레": "큰이십팔점박이무당벌레"
    }
    official_pest_name = synonyms.get(pest, pest)
    
    cache_key = official_pest_name
    now = time.time()
    
    if cache_key in ncpms_cache:
        cached_time, cached_data = ncpms_cache[cache_key]
        if now - cached_time < NCPMS_CACHE_TTL:
            return {"ncpms_data": cached_data}

    from app.core.config import settings
    api_key = settings.NCPMS_API_KEY
    if not api_key: 
        return {"ncpms_data": "NCPMS API 키(`NCPMS_API_KEY`)가 설정되지 않았습니다."}

    import requests
    import xml.etree.ElementTree as ET
    import re
    
    try:
        base_url = "http://ncpms.rda.go.kr/npmsAPI/service"
        search_params = {
            "apiKey": api_key, 
            "serviceCode": "SVC03", 
            "serviceType": "AA003", 
            "insectKorName": official_pest_name,
            "displayCount": "50"
        }
        search_resp = requests.get(base_url, params=search_params, timeout=10)
        text_resp = search_resp.text.strip()
        
        best_key = None
        fallback_key = None
        
        if text_resp.startswith("{"):
            data = json.loads(text_resp)
            service_data = data.get("service", {})
            if "returnAuthMsg" in service_data and service_data["returnAuthMsg"] not in ["NORMAL SERVICE.", "NORMAL SERVICE"]:
                return {"ncpms_data": f"API 인증 실패: {service_data['returnAuthMsg']}"}
                
            items = service_data.get("list", [])
            if isinstance(items, dict):
                items = [items]
                
            for item in items:
                res_pest = str(item.get("insectKorName", "")).strip()
                res_crop = str(item.get("cropName", "")).strip()
                insect_key = str(item.get("insectKey", ""))
                
                if res_pest and (official_pest_name in res_pest or res_pest in official_pest_name):
                    if not fallback_key:
                        fallback_key = insect_key
                    if crop and res_crop and crop in res_crop:
                        best_key = insect_key
                        break
        else:
            root = ET.fromstring(text_resp)
            for item in root.findall(".//item") + root.findall(".//list"):
                res_pest = item.findtext("insectKorName", "").strip()
                res_crop = item.findtext("cropName", "").strip()
                insect_key = item.findtext("insectKey", "")
                
                if res_pest and (official_pest_name in res_pest or res_pest in official_pest_name):
                    if not fallback_key:
                        fallback_key = insect_key
                    if crop and res_crop and crop in res_crop:
                        best_key = insect_key
                        break

        final_key = best_key or fallback_key
        if not final_key:
            return {"ncpms_data": f"NCPMS 정보 조회 결과, '{official_pest_name}'에 해당하는 데이터를 찾을 수 없습니다."}

        detail_params = {
            "apiKey": api_key, "serviceCode": "SVC07", "serviceType": "AA003", "insectKey": final_key
        }
        detail_resp = requests.get(base_url, params=detail_params, timeout=10)
        detail_text = detail_resp.text.strip()
        
        prevent_method, ecology_info, biology_method = "", "", ""
        if detail_text.startswith("{"):
            detail_data = json.loads(detail_text)
            service_data = detail_data.get("service", {})
            item = service_data
            if "list" in service_data:
                list_data = service_data["list"]
                if isinstance(list_data, list) and len(list_data) > 0:
                    item = list_data[0]
                elif isinstance(list_data, dict):
                    item = list_data
            prevent_method = item.get("preventMethod", "")
            ecology_info = item.get("ecologyInfo", "")
            biology_method = item.get("biologyPrvnbeMth", "")
        else:
            detail_tree = ET.fromstring(detail_resp.content)
            prevent_method = detail_tree.findtext(".//preventMethod", default="").strip()
            ecology_info = detail_tree.findtext(".//ecologyInfo", default="").strip()
            biology_method = detail_tree.findtext(".//biologyPrvnbeMth", default="").strip()
            
        def improve_readability(text: str) -> str:
            if not text: return ""
            text = text.replace(".", ". ")
            text = text.replace("~", "～")
            text = re.sub(r'\s+', ' ', text)
            return text.strip()
        
        info_parts = []
        if prevent_method:
            info_parts.append(f"### 재배 및 물리적 방제\n\n{improve_readability(prevent_method)}")
        if ecology_info:
            info_parts.append(f"### 생태 환경\n\n{improve_readability(ecology_info)}")
        if biology_method:
            info_parts.append(f"### 생물학적 방제\n\n{improve_readability(biology_method)}")
        
        html_tag_re = re.compile(r'<[^>]+>')
        final_info = "\n\n".join(info_parts)
        final_info = html_tag_re.sub('', final_info).replace("&nbsp;", " ").replace("&gt;", ">").replace("&lt;", "<").strip()
        
        if final_info:
            ncpms_cache[cache_key] = (now, final_info)
            return {"ncpms_data": final_info}
        
        return {"ncpms_data": "NCPMS 응답에서 방제 지침 정보를 찾을 수 없습니다. (데이터 없음)"}

    except Exception as e:
        return {"ncpms_data": f"NCPMS 통신 에러: {str(e)}"}

async def fetch_pesticide(state: DiagnosisState) -> dict:
    pest = state.get("pest", "알 수 없음")
    crop = state.get("crop", "알 수 없음")
    
    try:
        async with async_session() as db:
            query = select(PesticideProduct).where(
                PesticideProduct.target_name.like(f"%{pest}%"),
                PesticideProduct.crop_name.like(f"%{crop}%")
            ).limit(50)
            result = await db.execute(query)
            products = result.scalars().all()
            
            if products:
                # 메모.txt 템플릿에 맞는 grouped_results 형태의 JSON 생성
                grouped = {}
                for p in products:
                    ing_name = p.ingredient_or_formulation_name or "성분정보없음"
                    if ing_name not in grouped:
                        if len(grouped) >= 3: # 최대 3개의 성분만 반환
                            continue
                        grouped[ing_name] = {"ingredient_name": ing_name, "products": []}
                    
                    # 이미 동일한 상표명/제조사의 농약이 있다면 스킵 (중복 제거)
                    is_duplicate = False
                    for existing_prod in grouped[ing_name]["products"]:
                        if existing_prod["brand_name"] == (p.brand_name or "상표명없음"):
                            is_duplicate = True
                            break
                    if is_duplicate:
                        continue
                        
                    if len(grouped[ing_name]["products"]) >= 3: # 한 성분당 최대 3개의 제품만
                        continue
                        
                    grouped[ing_name]["products"].append({
                        "brand_name": p.brand_name or "상표명없음",
                        "corporation_name": p.corporation_name or "제조사없음",
                        "application_method": p.application_method or "정보없음",
                        "application_timing": p.application_timing or "정보없음",
                        "dilution_text": p.dilution_text or "해당 없음 (원액 또는 토양 혼화)",
                        "max_use_count_text": p.max_use_count_text or "정보없음"
                    })
                
                grouped_list = list(grouped.values())
                
                if grouped_list:
                    import json
                    return {"pesticide_data": json.dumps(grouped_list, ensure_ascii=False)}
                else:
                    return {"pesticide_data": "[]"}
            else:
                return {"pesticide_data": "[]"}
    except Exception as e:
        print(f"Pesticide DB Cache error: {e}")
        return {"pesticide_data": "[]"}

async def generate_diagnosis(state: DiagnosisState) -> dict:
    from app.core.config import settings
    api_key = settings.OPENROUTER_API_KEY
    model_name = settings.OPENROUTER_PEST_RAG_MODEL

    # API 키가 없거나 dummy일 경우 목업 데이터 반환
    if api_key == "dummy" or not api_key:
        fallback_json = {
            "result_text": "API 키가 설정되지 않아 가데이터를 출력합니다."
        }
        return {"analysis_result": fallback_json}

    import httpx
    
    # httpx를 통해 HTTP/1.1 강제로 Cloudflare의 HTTP/2 버그(RemoteProtocolError) 원천 차단
    custom_async_client = httpx.AsyncClient(
        http1=True,
        http2=False,
        timeout=httpx.Timeout(180.0, connect=20.0)
    )

    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=settings.OPENROUTER_URL,
        temperature=0.0,
        max_retries=2,
        http_async_client=custom_async_client
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", """
너는 입력된 JSON 데이터를 정해진 텍스트 템플릿에 매핑하는 '템플릿 엔진(Template Engine)'이다.
절대 스스로 생각해서 문장을 지어내거나 단어, 줄바꿈을 임의로 바꾸지 마라.

[과거 대화 내역]
{history}

[입력 데이터]
{json_text}
질문: {user_question}


🚨 [작동 모드 판단 규칙]
1. 입력 데이터(JSON)에 "pesticide_summary"가 존재하면 -> <모드 A> 실행
2. 입력 데이터가 비어있거나, 일반적인 농업/약제 관련 질문이면 -> <모드 B> 실행

▶ <모드 A: 템플릿 엔진 모드 (엄격한 데이터 치환)>
아래 [출력 템플릿]의 텍스트와 빈 줄을 100% 그대로 복사하되, `[[ ]]` 안의 값만 JSON 데이터로 치환한다.

* 절대 규칙 1 (원문 100% 보존): JSON의 텍스트를 임의로 수정/편집하지 마라. (예: preventive_info 본문의 빈 줄을 없애거나 ■ 기호를 함부로 추가하지 마라. 단어를 바꾸지 마라). 반드시 원본 문자열 그대로 붙여넣어라. 특히 `preventive_info` 내의 "생태 환경" 등 항목 아래에 임의로 "방제제 요약 테이블"이나 표, 목록 등을 절대 만들어 넣지 마라.
* 절대 규칙 2 (HTML 보존): 제공된 `pesticide_summary` 및 `weather_summary`의 HTML 코드를 절대 수정하지 말고 마크다운 내에 그대로 출력해라.
* 절대 규칙 3 (사족 및 훼손 금지): 출력물의 앞뒤에 설명, 인사말을 절대 넣지 마라. 결과물은 반드시 제공된 마크다운 템플릿(헤더 `##`, 리스트 `- ` 등)을 그대로 유지해야 한다.
* 절대 규칙 4: 치환이 끝난 후 `[[ ]]` 기호는 출력물에서 완벽히 삭제한다.
* 절대 규칙 5 (추가 정보 금지): "## ⚠️ 공지:" 섹션으로 출력이 반드시 끝나야 한다. 그 뒤에 "그 밖의 정보", "참고", "추가 데이터", "pesticide_summary", JSON 덩어리 등 어떤 형태로든 내용을 더 붙이지 마라. 원본 JSON 데이터를 통째로 출력하지 마라.
  * 절대 규칙 6 (언어/형식): 모든 대답은 존댓말(한국어)로 친절하게 작성하며, 결과물 중간에 === 나 --- 같은 구분 기호를 임의로 삽입하여 출력하지 마라.

▶ <모드 B: 일반 대화 모드>
템플릿을 완전히 무시하고, 사용자의 질문에 친절하고 상세한 농업 전문가로서 직접 대답한다.


[모드 A 완벽 처리 예시] - 반드시 이 예시의 패턴을 100% 모방하여 답변해라. (환각 방지 핵심: 방제 지침 안에 표나 요약 등 내용을 추가하지 말 것)
(랭플로우 에러 방지를 위해 괄호를 생략한 데이터 구조)
입력 데이터:
"region": "서울", "crop_display": "배추", "pest": "벼룩잎벌레"
"preventive_info": "### 생태 환경\\n\\n이 해충의 유충은 땅속에서 경과하고 성충은 잎을 갉아 먹는다.\\n\\n### 재배 및 물리적 방제\\n\\n잡초를 제거한다."
"weather_summary": "<div class='grid grid-cols-1 mb-3'>날씨 카드 HTML</div>"
"pesticide_summary": "<div class='bg-gray-50 border...'>농약 카드 HTML</div>"

출력 결과물 (마크다운 형식 적용, ## ⚠️ 공지 섹션으로 끝남):
## 🌿 서울 지역의 배추 벼룩잎벌레 방제 솔루션입니다.

## 🧪 권장 농약 목록 (출처: 농촌진흥청 농약안전정보시스템)

<div class='bg-gray-50 border...'>농약 카드 HTML</div>

## 🚜 객관적 예방 및 재배적 방제 지침 (출처: 국가농작물병해충관리시스템 NCPMS)

### 생태 환경

이 해충의 유충은 땅속에서 경과하고 성충은 잎을 갉아 먹는다.

  ### 재배 및 물리적 방제\n\n잡초를 제거한다.

  ( 주의: 생태 환경이나 방제 지침 아래에 외부 지식을 동원해 방제제 요약 항목이나 표(Table) 등을 절대 추가하지 마라!)

## 💡 실시간 환경 맞춤 조언 (출처: 기상청 단기예보 서비스)

- 날씨 요약: 
  <div class='grid grid-cols-1 mb-3'>날씨 카드 HTML</div>
- 조언: 비 예보가 없고(0%) 바람도 1.5m/s로 잔잔해지는 내일(21일) 기온이 크게 오르기 전 18~23℃ 사이의 서늘한 시간대를 택해 살포하는 것을 가장 권장합니다.


## 🤖 AI 총평 및 방제 전략

- 최적 살포 시기: 4월 21일 오후와 같이 바람이 잔잔(1.5m/s)하고 강수 확률이 없는 시간대를 노려 약제 유실을 막으세요.
- 권장 방제법: 초기 방제가 필수적이므로, 다이아지논 입제(듀크)를 파종 전 토양에 철저히 혼화 처리하여 유충을 사전에 억제하세요.
- 재배 관리: 토양 속에 숨어 지내는 유충의 생태를 고려해, 밭을 갈아엎어 해충이 자연광에 노출되도록 하는 물리적 방제를 꼭 병행해야 합니다.

## ⚠️ 공지: 제공된 정보는 공공데이터에 기반한 참고용입니다. 농약 사용 전 반드시 제품 라벨의 규정을 확인하십시오.

[주의: 위 "## ⚠️ 공지" 섹션 이후에는 절대로 아무런 텍스트, JSON 데이터, "pesticide_summary", "그 밖의 정보" 등을 출력하지 마라. 출력이 여기서 완전히 끝나야 한다.]


[출력 템플릿] (※ 주의: 이 줄과 아래 점선은 절대 출력하지 마라)
## 🌿 [[region]] 지역의 [[crop_display]] [[pest]] 방제 솔루션입니다.

## 🧪 권장 농약 목록 (출처: 농촌진흥청 농약안전정보시스템)

[[pesticide_summary]]

## 🚜 객관적 예방 및 재배적 방제 지침 (출처: 국가농작물병해충관리시스템 NCPMS)

[[preventive_info]]

## 💡 실시간 환경 맞춤 조언 (출처: 기상청 단기예보 서비스)

- 날씨 요약: [[weather_summary]]
- 조언: [[날씨(기온, 강수확률, 최대 풍속) 데이터를 구체적으로 분석하여, 농약 살포 최적일과 피해야 할 시간대, 주의사항 등을 2~3문장 이상으로 매우 구체적이고 전문적으로 작성.]]

## 🤖 AI 총평 및 방제 전략

[[위에서 제공된 권장 농약 사용법, 방제 지침(예방/물리/생태), 기상청 날씨 조언 등을 모두 종합하여, 사용자가 지금 당장 실천해야 할 핵심적인 방제 전략을 3~4개의 명확한 개조식(- )으로 요약. 각 항목은 "최적 살포 시기: ", "권장 방제법: ", "재배 관리: " 와 같이 제목 뒤에 꼭 콜론(:)을 붙여 가독성 좋게 작성할 것. 반말을 쓰지 말고 반드시 친절한 존댓말(~해요, ~하십시오)로 작성해라.]]

## ⚠️ 공지: 제공된 정보는 공공데이터에 기반한 참고용입니다. 농약 사용 전 반드시 제품 라벨의 규정을 확인하십시오.
--------------------------------------------------
"""),
        ("user", "데이터를 기반으로 템플릿 엔진의 역할을 수행하라.")
    ])

    from langchain_core.output_parsers import StrOutputParser
    chain = prompt | llm | StrOutputParser()
    
    import json
    
    try:
        weather_info = state.get("weather_data", {})
        if isinstance(weather_info, str):
            weather_info = {}

        # 향후 3~4일치 날씨 요약을 모두 포함하도록 변경
        weather_summary = "데이터 없음"
        if "daily_forecast" in weather_info:
            daily = weather_info["daily_forecast"]
            html_cards = ["<div class='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 my-3'>"]
            for date_key, td_data in daily.items():
                d_str = f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}"
                min_t = td_data['min_temp']
                max_t = td_data['max_temp']
                rain = td_data['max_precip_prob']
                wind = td_data.get('max_wind_speed', 0.0)
                cond = td_data.get('condition', '☀️ 맑음')
                
                card = f"<div class='bg-blue-50/50 border border-blue-100 rounded-xl p-3 flex flex-col items-center justify-center text-center shadow-sm'><div class='font-bold text-gray-700 mb-1 text-[13px]'>{d_str}</div><div class='font-medium text-blue-800 text-[13px] mb-1'>{cond}</div><div class='text-xl flex flex-col items-center justify-center font-black text-blue-600 mb-1'><span class='text-[10px] font-normal text-gray-500 bg-white px-2 py-0.5 rounded-full shadow-sm mb-1 mt-1'>최저/최고</span><div>{min_t}°<span class='text-gray-400 text-sm font-normal mx-1'>/</span>{max_t}°</div></div><div class='flex flex-col gap-0.5 text-xs text-gray-600 mt-1'><span class='flex items-center justify-center bg-white px-2 py-0.5 rounded border border-blue-100 text-blue-800 font-medium'>☔ 강수 {rain}%</span><span class='flex items-center justify-center bg-white px-2 py-0.5 rounded border border-blue-100 text-blue-800 font-medium'>💨 풍속 {wind}m/s</span></div></div>"
                html_cards.append(card)
            html_cards.append("</div>")
            weather_summary = "".join(html_cards)
            
            temp = "다일 데이터"
            rain = "다일 데이터"
        else:
            temp = "데이터 없음"
            rain = "데이터 없음"
        
        try:
            grouped_results = json.loads(state.get("pesticide_data", "[]"))
            pest_html = ""
            for item in grouped_results:
                ing = item.get("ingredient_name", "")
                pest_html += f"<div class='bg-gray-50 border border-gray-200 rounded-xl p-4 my-3'><div class='font-bold text-primary mb-3 text-base flex items-center gap-2'><span>💊</span> 성분: {ing}</div><div class='grid grid-cols-1 md:grid-cols-2 gap-3'>"
                for prod in item.get("products", []):
                    bname = prod.get("brand_name", "")
                    cname = prod.get("corporation_name", "")
                    method = prod.get("application_method", "")
                    timing = prod.get("application_timing", "")
                    dilution = prod.get("dilution_text", "")
                    use_cnt = prod.get("max_use_count_text", "")
                    pest_html += f"<div class='bg-white rounded-lg p-3 shadow-none border border-gray-200 flex flex-col h-full'><div class='font-bold text-gray-800 text-sm mb-3 flex items-center flex-wrap gap-2'><span class='text-primary text-[15px]'>{bname}</span><span class='text-[11px] font-normal text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full'>{cname}</span></div><div class='grid grid-cols-2 gap-2 mt-auto'><div class='flex flex-col p-1.5 bg-gray-50/50 rounded'><span class='text-gray-400 mb-0.5 text-[10px]'>사용 방법</span><span class='font-medium text-gray-700 text-xs'>{method}</span></div><div class='flex flex-col p-1.5 bg-gray-50/50 rounded'><span class='text-gray-400 mb-0.5 text-[10px]'>사용 시기</span><span class='font-medium text-gray-700 text-xs'>{timing}</span></div><div class='flex flex-col p-1.5 bg-gray-50/50 rounded'><span class='text-gray-400 mb-0.5 text-[10px]'>희석 배수</span><span class='font-medium text-gray-700 text-xs'>{dilution}</span></div><div class='flex flex-col p-1.5 bg-gray-50/50 rounded'><span class='text-gray-400 mb-0.5 text-[10px]'>사용 횟수</span><span class='font-medium text-gray-700 text-xs'>{use_cnt}</span></div></div></div>"
                pest_html += "</div></div>"
            if not pest_html:
                pest_html = "권장 농약 정보가 없습니다."
        except:
            pest_html = "권장 농약 정보가 없습니다."

        full_region = state.get("region", "서울")
        parts = full_region.split()
        if len(parts) >= 2:
            display_region = f"{parts[0]} {parts[1]}" 
        else: 
            display_region = parts[0] if parts else "서울"

        json_payload = {
            "region": display_region,
            "crop_display": state.get("crop") if state.get("crop") else "전체 작물",
            "pest": state.get("pest"),
            "temp": temp,
            "rain": rain,
            "weather_summary": weather_summary,
            "preventive_info": state.get("ncpms_data") or "데이터 없음",
            "pesticide_summary": pest_html
        }
        
        json_text = json.dumps(json_payload, ensure_ascii=False)

        # Cloudflare 504 타임아웃 우회를 위한 스트리밍(Chunk) 수신 방식 적용
        raw_response = ""
        async for chunk in chain.astream({
            "history": "과거 대화 내역 없음",
            "user_question": f"{state.get('crop')} {state.get('pest')} 방제 방법 알려줘",
            "json_text": json_text
        }):
            raw_response += chunk

        # Remove any unfilled brackets if left behind
        response = re.sub(r'\[\[.*?\]\]', '', raw_response)
        
        # Remove stray markdown codeblock backticks often hallucinated around HTML
        response = response.replace('```html\n', '').replace('```html', '').replace('```', '')
        
        # Remove trailing double quote from HTML block if the LLM hallucinates it
        response = response.replace('</div>"', '</div>')
        
        # LLM이 아주 긴 HTML을 출력하다가 3번째 요소의 </div> 닫는 태그를 누락/생략하여 
        # 아래쪽 섹션(NCPMS)이 농약 카드 테두리(bg-gray-50)에 병합되는 UI 버그가 자주 발생함.
        # 이를 100% 방지하기 위해 생성된 본문 사이의 망가진 HTML을 원래의 백엔드 pest_html 문자열로 통째로 덮어씌움.
        pattern = re.compile(r'(## 🧪 권장 농약 목록 .*?\n)(.*?)(## 🚜 객관적 예방 및 재배적 방제 지침)', re.DOTALL)
        match = pattern.search(response)
        if match:
            response = response[:match.start(2)] + f"\n{pest_html}\n\n" + response[match.end(2):]

        # 'grouped_results' 같은 JSON 잔재가 환각으로 출력되었을 경우 잘라내기
        if "## ⚠️ 공지" in response:
            parts = response.split("## ⚠️ 공지")
            response = parts[0] + "## ⚠️ 공지" + parts[1].split("\n")[0]
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"LLM Error: {type(e).__name__} - {e}")
        response = f"AI 엔진 분석 중 오류가 발생했습니다: {type(e).__name__}"

    return {"analysis_result": {"result_text": response}}

# Langgraph compilation
workflow = StateGraph(DiagnosisState)

workflow.add_node("fetch_weather", fetch_weather)
workflow.add_node("fetch_ncpms", fetch_ncpms)
workflow.add_node("fetch_pesticide", fetch_pesticide)
workflow.add_node("generate_diagnosis", generate_diagnosis)

workflow.add_edge(START, "fetch_weather")
workflow.add_edge("fetch_weather", "fetch_ncpms")
workflow.add_edge("fetch_ncpms", "fetch_pesticide")
workflow.add_edge("fetch_pesticide", "generate_diagnosis")
workflow.add_edge("generate_diagnosis", END)

diagnosis_app = workflow.compile()

async def run_diagnosis(pest: str, crop: str, region: str):
    """
    이 함수는 더 이상 ainvoke로 한 번에 결과를 반환하지 않고,
    LangGraph의 각 노드 완료마다 상태를 stream(yield) 합니다.
    """
    initial_state = {
        "pest": pest,
        "crop": crop,
        "region": region,
        "weather_data": None,
        "ncpms_data": None,
        "pesticide_data": None,
        "analysis_result": None
    }
    
    async for event in diagnosis_app.astream(initial_state):
        node_name = list(event.keys())[0]
        yield node_name, dict(event[node_name])
