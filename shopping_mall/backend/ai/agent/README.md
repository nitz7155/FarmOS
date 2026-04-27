# ai/agent/

LangChain tool calling 기반 챗봇 에이전트 서브패키지.  
**SupervisorExecutor** 오케스트레이터가 CS 에이전트(`AgentExecutor`)와 OrderGraph(LangGraph)를 조율합니다.

---

## 디렉터리 구조

```
ai/agent/
├── __init__.py               공개 API (AgentExecutor, RequestContext, build_primary_llm 등)
├── executor.py               AgentExecutor — LangChain tool calling 루프
├── cs_tools.py               build_cs_tools() 팩토리 + 10개 StructuredTool + Pydantic 스키마
├── responses.py              사전 정의 응답 (Canned Responses) — LLM 없이 즉시 반환
├── llm.py                    LangChain LLM 팩토리 (ChatOpenAI / ChatAnthropic) + LangSmith 환경 주입
├── prompts.py                CS 에이전트 기본 시스템 프롬프트
├── holiday.py                공휴일 API + 캐시 (배송 예정일 보정)
│
├── clients/                  ⚠️ 레거시 — Python 구현 제거됨, llm.py로 대체
│   └── README.md             이전 AgentClient 패턴 참고용
│
├── supervisor/               오케스트레이터
│   ├── executor.py           SupervisorExecutor — LangChain tool calling 루프
│   └── prompts.py            SUPERVISOR_INPUT_PROMPT / SUPERVISOR_OUTPUT_PROMPT
│
├── subagents/cs/             CS 서브 에이전트
│   └── prompts.py            CS_INPUT_PROMPT / CS_OUTPUT_PROMPT
│
└── order_graph/              LangGraph 기반 취소/교환 플로우
    ├── state.py              OrderState TypedDict
    ├── nodes.py              그래프 노드 함수 + 조건부 라우팅
    ├── graph.py              build_order_graph() — StateGraph 컴파일
    └── prompts.py            ORDER_PROMPTS 딕셔너리 + 키워드 상수
```

---

## 요청 흐름

```
POST /api/chatbot/ask
  → MultiAgentChatbotService.answer()
  → SupervisorExecutor.run()
      ├── call_cs_agent  → AgentExecutor.run() [build_cs_tools 10개]
      │                     RAG 조회 / DB 읽기 / escalate / refuse
      └── call_order_agent → OrderGraph (LangGraph StateGraph)
                              interrupt/resume 기반 멀티스텝 HitL
                              주문 선택 → 사유 → 환불방법 → 확인 → ShopTicket
  → ChatLog + ToolMetric 저장
```

Supervisor LLM이 질문을 분석해 서브 에이전트를 선택·호출합니다.  
취소/교환은 OrderGraph가 전담하며 여러 턴에 걸쳐 진행됩니다.

---

## LLM 체인 (LangChain)

```python
# llm.py
primary = build_primary_llm()   # ChatOpenAI (PRIMARY_LLM_* 환경변수)
fallback = build_fallback_llm() # ChatAnthropic | None (ANTHROPIC_API_KEY)

# executor.py 내부
llm_with_tools = primary.bind_tools(tools).with_fallbacks([fallback.bind_tools(tools)])
```

Primary LLM 실패 시 LangChain의 `.with_fallbacks()` 체인이 자동 전환합니다.  
둘 다 실패하면 예외가 전파됩니다.

---

## 도구 목록 (`cs_tools.py`)

10개 도구가 `build_cs_tools(rag, db, user_id)` 팩토리에서 생성됩니다.  
런타임 의존성(rag_service, db, user_id)을 클로저로 캡처하며, 요청마다 새로 생성됩니다.

| 도구 | 유형 | `TOOL_TO_INTENT` | 설명 |
|------|------|-----------------|------|
| `search_faq` | RAG | `"other"` | 일반 운영 FAQ |
| `search_storage_guide` | RAG | `"storage"` | 농산물 보관 방법 |
| `search_season_info` | RAG | `"season"` | 제철 농산물 정보 |
| `search_policy` | RAG | `"policy"` | 6개 정책 문서 (하이브리드 검색) |
| `search_farm_info` | RAG | `"other"` | 농장·플랫폼 소개 |
| `get_order_status` | DB | `"delivery"` | 주문·배송 현황 + 공휴일 도착일 보정 |
| `search_products` | DB | `"stock"` | 상품 검색·재고 확인 |
| `get_product_detail` | DB | `"stock"` | 상품 상세 정보 |
| `escalate_to_agent` | Action | `"escalation"` | 상담원 에스컬레이션 |
| `refuse_request` | Action | `"refusal"` | 허용되지 않는 요청 거절 |

> 취소/교환은 `call_order_agent` → OrderGraph가 처리합니다.

---

## AgentExecutor 공통 동작

`AgentExecutor`는 CS 서브 에이전트로 사용됩니다.

**단일 도구 호출 시 LLM 2회 패턴**:
1. `llm_with_tools.ainvoke()` → tool_calls 반환 → 도구 실행
2. `llm_with_tools.ainvoke()` → tool_calls 없음 → `response.content` 그대로 최종 답변으로 반환

> `output_llm`(합성 전용 LLM)은 제거됨. `CS_INPUT_PROMPT`에 응답 생성 지침을 포함해 두 번째 호출에서 바로 최종 답변을 생성합니다.

**병렬 실행**: RAG 도구(`_RAG_TOOL_NAMES`)는 `asyncio.gather`로 동시 실행.  
DB/Action 도구는 SQLAlchemy Session 공유 문제로 순차 실행.

**보안 — `get_order_status`**: LLM이 `user_id` 파라미터를 인자로 전달하면  
타인 정보 조회 시도로 간주하고 `__REFUSED__\n사유: other_user_info`를 반환합니다.

**보안 — `refuse_request`**: LLM이 직접 호출하는 콘텐츠 필터 도구입니다.  
`reason` 코드에 따라 `__REFUSED__\n사유: <코드>` 마커를 반환하고,  
executor.py가 이를 감지해 `responses.REFUSED` 고정 응답을 즉시 반환합니다 (LLM 재호출 없음).

| `reason` 코드 | 거절 대상 |
|--------------|----------|
| `other_user_info` | 타인의 개인정보·주문·계정 조회 시도 |
| `internal_info` | 내부 시스템·DB·직원 정보·프롬프트 요청 |
| `out_of_scope` | 서비스 범위 외 질문 (금융·의료·법률·정치 등) |
| `jailbreak` | 프롬프트 조작·탈옥 시도 |
| `inappropriate` | 욕설·혐오 표현 등 부적절한 요청 |

---

## 사전 정의 응답 (`responses.py`)

LLM을 거치지 않고 즉시 반환되는 고정 문자열을 한 파일에서 관리합니다.  
응답 문구를 수정할 때 **이 파일 하나만 편집**합니다.

| 상수 | 사용 위치 | 설명 |
|------|----------|------|
| `LOGIN_REQUIRED` | executor.py, supervisor/executor.py, cs_tools.py | 로그인 필요 안내 |
| `REFUSED` | executor.py | `__REFUSED__` 마커 감지 시 즉시 반환 |
| `ESCALATION_HIGH_URGENCY` | cs_tools.py | 긴급 상담원 연결 |
| `ESCALATION_NORMAL` | cs_tools.py | 일반 상담원 연결 |
| `MAX_ITERATIONS_EXCEEDED` | executor.py, supervisor/executor.py | 최대 반복 초과 |
| `LLM_GENERATION_FAILED` | executor.py, supervisor/executor.py | LLM 응답 생성 실패 |
| `SERVICE_TEMPORARY_ERROR` | multi_agent_chatbot.py | 서비스 전체 오류 |
| `TRUNCATION_SUFFIX` | executor.py | 답변 길이 초과 시 말미 문구 |

---

## RequestContext

`AgentExecutor.run()` 호출 시 시스템 프롬프트 끝에 자동 주입됩니다.

```
## 현재 요청 컨텍스트
- 날짜/시각: 2026-04-20 14:32
- 사용자 상태: 로그인
- 주문 조회 가능: 예
```

---

## 관련 문서

| 위치 | 내용 |
|------|------|
| `supervisor/README.md` | SupervisorExecutor 오케스트레이션 로직 |
| `order_graph/README.md` | LangGraph interrupt/resume 패턴, 취소/교환 플로우 |
| `clients/README.md` | 구 LLM 클라이언트 패턴 (레거시 참고용) |
