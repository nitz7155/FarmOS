# ESP8266 LED Sync Planning Document

> **Summary**: ESP8266 펌웨어를 기존 Relay Server 폴링 계약(iot-manual-control)에 정합화하여, 프론트엔드·물리버튼·AI 3개 소스 중 누가 조작해도 ESP8266의 LED가 단일 상태 기준으로 양방향 동기화되도록 한다.
>
> **Project**: FarmOS - IoT Relay
> **Feature**: esp8266-led-sync
> **Version**: 0.1.0
> **Author**: clover0309
> **Date**: 2026-04-21
> **Status**: Draft
> **Depends On**: `iot-manual-control` (Server + Frontend 완료분), `iot-relay-server-postgres-patch`
> **Target Files**:
> - `FarmOS/DH11_KY018_WiFi/DH11_KY018_WiFi.ino` (수정)
> - `iot_relay_server/app/control_routes.py` (미세 보강, 필요시)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 ESP8266 펌웨어는 (1) 자체 HTTP 서버(`/control`)를 포트 80에 열어 프론트엔드에서 직접 제어하도록 설계되어 있어 터널/NAT 환경에서는 도달 불가이고, (2) 센서 POST 페이로드에 actuator 상태를 끼워 보내 서버의 `/api/v1/control/*` 계약과 어긋난다. 그 결과 프론트엔드 토글 ↔ 물리 버튼 ↔ LED 3자 동기화가 성립하지 않는다. |
| **Solution** | ESP8266의 로컬 HTTP 서버를 제거하고 서버 주도 **HTTP 폴링 모델**로 전환한다. 3개 물리 버튼(환기/조명/차광)은 인터럽트로 감지해 `POST /api/v1/control/report`로 즉시 보고하고, 2초마다 `GET /api/v1/control/commands?device_id=`로 대기 명령을 수신하여 LED를 구동한 뒤 `POST /api/v1/control/ack`로 확정한다. 관수 LED는 서버 측 `irrigation.active`를 그대로 미러링한다. |
| **Function/UX Effect** | 프론트엔드에서 토글을 누르면 5초 내 현장 LED가 반응하고, 현장에서 버튼을 누르면 2초 내 프론트엔드 UI가 반영된다. AI Agent가 바꾼 상태도 동일 파이프라인으로 LED에 반영되어, "누가 바꿨는지"와 무관하게 LED가 곧 현재 상태의 시각적 증거가 된다. |
| **Core Value** | 물리 세계(LED·버튼)와 디지털 세계(대시보드·AI)의 **Single Source of Truth 정합성**. 1인 농업인이 어디서 조작하든 현장 LED만 보면 현재 제어 상태를 즉시 확인할 수 있고, 소스 간 충돌(수동 잠금)도 서버에서 일관 관리된다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 기존 `iot-manual-control` 설계의 ESP8266 단(Step 2)이 미구현 상태라 서버·프론트엔드만 완성된 상태의 반쪽 시스템을 끝내 닫기 위함 |
| **WHO** | FarmOS 1인 농업인 — 현장 버튼 3개(환기/조명/차광) + 대시보드 토글 + AI 자동화 3개 경로 사용 |
| **RISK** | ESP8266 메모리·스택 제약, 폴링 주기 vs 반응성 트레이드오프, WiFi 끊김 시 상태 불일치, `ICACHE_RAM_ATTR` deprecated 경고, D0/D2/D8 사용 시 부팅 핀 주의 |
| **SUCCESS** | 프론트엔드 토글 → ≤ 5s LED 반응 / 물리 버튼 → ≤ 2s 프론트엔드 반영 / 24h 연속 구동 무재부팅 / 네트워크 회복 후 상태 자동 재수렴 |
| **SCOPE** | In: 환기(fan)·조명(light)·차광(shade) 3버튼 양방향 + 관수(water) LED 미러링. Out: 버튼 추가 장착(관수 버튼), MQTT/WebSocket 전환, OTA 펌웨어 업데이트 |

---

## 1. Overview

### 1.1 Purpose

현재 ESP8266 펌웨어(`DH11_KY018_WiFi.ino`)를 Relay Server의 기존 제어 API 계약(`app/control_routes.py`, `app/control_store.py`)에 정합화하여, **프론트엔드·물리 버튼·AI 3자가 동일한 상태 기준 하에 LED 시각 피드백을 공유**하도록 만든다. 본 기능은 `iot-manual-control`의 Step 2(ESP8266 펌웨어)에 해당하지만, 서버/프론트 완성 이후 별도 관리 단위로 분리한다.

### 1.2 Background

- **서버 현황 (완성)**: `iot_relay_server`는 `control_state`(in-memory) + `pending_commands`(큐) 모델로 동작. `POST /api/v1/control`(프론트) → `add_pending_command()` → ESP8266이 `GET /api/v1/control/commands`로 폴 → LED 반영 후 `POST /api/v1/control/ack`로 큐 정리. 반대 방향은 ESP8266의 `POST /api/v1/control/report`로 전달.
- **프론트엔드 현황 (완성)**: `ManualControlPanel` + `useManualControl` 훅이 `/api/v1/control` POST + SSE `control` 이벤트 구독으로 양방향 반영.
- **ESP8266 현황 (Gap)**:
  - `ESP8266WebServer server(80)` + `/control` 엔드포인트를 로컬 노출 → 터널(`iot.lilpa.moe`) 뒤에서는 프론트에서 도달 불가.
  - `sendToServer()`가 `POST /api/v1/sensors`에 `actuators` 필드를 끼워 보내지만 서버는 이 필드를 해석하지 않음(스키마: `SensorDataIn.sensors`만).
  - `water` 버튼은 펌웨어 코드상 존재하지 않으나 LED는 구동됨 → 서버 상태 미러링 필요.
- **보조 배경**: 인터럽트 핸들러의 `ICACHE_RAM_ATTR`는 ESP8266 코어 3.0+에서 `IRAM_ATTR`로 교체 권고.

### 1.3 Related Documents

- `docs/01-plan/features/iot-manual-control.plan.md`
- `docs/02-design/features/iot-manual-control.design.md`
- `docs/iot-relay-server-plan.md`
- `docs/iot-relay-server-postgres-patch.md`
- `docs/esp8266-todo.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] ESP8266 내장 `ESP8266WebServer` 제거 및 80 포트 해제 (서버 측 계약으로 일원화)
- [ ] `GET /api/v1/control/commands?device_id=esp8266-01` 폴링 루프 (주기 2s, WiFi 회복 시 즉시 1회)
- [ ] `POST /api/v1/control/report` (버튼 이벤트 즉시 전송, source=`button`)
- [ ] `POST /api/v1/control/ack` (수신 명령 확정, 큐 정리)
- [ ] 3개 버튼 → 3개 control_type 매핑: `BTN_FAN`→`ventilation`, `BTN_LIGHT`→`lighting`, `BTN_SHADE`→`shading`
- [ ] 4개 LED → 서버 `led_on` 상태 미러링: 환기/조명/차광 + 관수(읽기 전용)
- [ ] 센서 POST 페이로드에서 `actuators` 필드 제거 (관심사 분리)
- [ ] `IRAM_ATTR` 마이그레이션 + 디바운스(소프트웨어) 보강
- [ ] 실패/재시도 정책 (HTTP 타임아웃, 지수 백오프 폴링)

### 2.2 Out of Scope

- [ ] 관수용 물리 버튼 추가 (LED만 미러링)
- [ ] MQTT/WebSocket/SSE 클라이언트 전환
- [ ] OTA 펌웨어 업데이트
- [ ] TLS/HTTPS 지원
- [ ] 서버 측 신규 엔드포인트 추가 (기존 계약 사용)

### 2.3 Non-Goals

- 새로운 control_type 추가
- 인증 체계 변경 (`X-API-Key` 유지)
- Postgres 스키마 변경

---

## 3. Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | ESP8266은 2초 주기로 `GET /api/v1/control/commands?device_id=esp8266-01` (header: `X-API-Key`) 호출한다 | Must |
| FR-02 | 수신된 명령의 `control_type ∈ {ventilation, lighting, shading, irrigation}`만 해석하고, 그 외는 무시 후 ack 처리 | Must |
| FR-03 | LED 상태는 서버 상태(`active` 또는 `led_on`) 기준으로 결정되며, 펌웨어 로컬 상태는 서버 응답에 덮어쓰기된다 | Must |
| FR-04 | 명령 적용 직후 `POST /api/v1/control/ack { device_id, acknowledged_types: [...] }` 호출 | Must |
| FR-05 | 물리 버튼 눌림 시 인터럽트로 즉시 플래그 set → 메인 루프에서 `POST /api/v1/control/report { device_id, control_type, state, source: "button" }` 전송 | Must |
| FR-06 | 버튼 report의 `state` 형식: 환기 `{ "active": bool, "fan_speed": 0|50 }`, 조명 `{ "on": bool, "brightness_pct": 0|100 }`, 차광 `{ "shade_pct": 0|100 }` | Must |
| FR-07 | 센서 POST(`/api/v1/sensors`)에서 `actuators` 필드 제거, `sensors`만 전송 | Must |
| FR-08 | 관수(`irrigation`) LED는 폴링 응답의 `active`/`led_on`을 미러링 (버튼 없음) | Must |
| FR-09 | WiFi 끊김 시 재접속 루프(최대 10회, 각 1초) 및 복구 후 즉시 폴 1회 수행 | Should |
| FR-10 | 모든 HTTP 요청에 `X-API-Key: farmos-iot-default-key` + `Bypass-Tunnel-Reminder: true` 헤더 포함 | Must |
| FR-11 | 버튼 디바운스: 인터럽트 + 200ms 쿨다운으로 중복 토글 방지 | Should |

---

## 4. Non-Functional Requirements

| Aspect | Target |
|--------|--------|
| 반응성 (프론트 → LED) | ≤ 5s (폴링 주기 2s + HTTP RTT) |
| 반응성 (버튼 → 프론트) | ≤ 2s (즉시 POST + SSE broadcast) |
| 가용성 | 24h 연속 구동, 무재부팅. WiFi 끊김 ≤ 30s 자동 복구 |
| 메모리 | 힙 여유 ≥ 8KB 유지 (ESP8266 free heap) |
| 보안 | 모든 제어 요청 `X-API-Key` 검증 (기존 서버 미들웨어 사용) |
| 관측성 | Serial 로그 포맷: `[POLL] [BTN] [LED] [HTTP]` 접두사로 구분 |

---

## 5. Success Criteria

1. **양방향 동기화**: 프론트엔드 "환기 ON" 토글 → 5초 내 ESP8266 D1 LED 점등 / ESP8266 BTN_FAN 1회 누름 → 2초 내 프론트 UI가 ON으로 전환.
2. **AI 경로 일관성**: `POST /api/v1/ai-agent/override` 또는 규칙 엔진이 `lighting.on=true` 설정 → 5초 내 D2 LED 점등.
3. **수동 잠금 동작**: 버튼 토글 후 `locked=true` 상태에서 AI 규칙이 해당 control_type을 덮어쓰지 않음 (기존 서버 로직 검증).
4. **네트워크 회복**: WiFi AP 재시작(≤ 20s) 후 ESP가 자동 재접속하고 현재 서버 상태로 LED 재수렴.
5. **관심사 분리**: `/api/v1/sensors` POST 페이로드에 `actuators` 필드가 더 이상 포함되지 않음 (서버 로그로 검증).
6. **24h 스트레스**: Serial 모니터에 `DHT11 Not Found` 외 에러 누적 없음, 힙 leak 없음(free heap ±1KB 변동).

---

## 6. Constraints

### 6.1 Hardware

- **ESP8266 NodeMCU v1.0**
- 버튼: D7(FAN), D6(LIGHT), D3(SHADE) — 내부 풀업, FALLING 엣지
- LED: D1(FAN), D0(WATER, 내장, 로직 반전), D2(LIGHT), D8(SHADE)
- ⚠ **D8은 부팅 핀**: 외부 풀다운 필수. 현 회로에서 기 적용 중으로 가정
- 센서: DHT11(D4), KY-018 LDR(A0)

### 6.2 Network

- 기존 WiFi SSID `AndroidHotspot2893`, 서버 호스트 `http://iot.lilpa.moe`
- HTTP only (TLS 미지원), 터널 뒤 존재 → **클라이언트 발신**(폴링/리포트)만 허용

### 6.3 API (고정)

- 인증: `X-API-Key: farmos-iot-default-key`
- 기저 path: `/api/v1` (기존 서버 라우터 그대로)
- control_type 화이트리스트: `ventilation | irrigation | lighting | shading`

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| 폴링 주기 2s로 반응 지연 | Medium | 버튼은 즉시 report로 보완, 프론트는 SSE 경로로 UI 측 즉시 반영 |
| WiFi 끊김 시 상태 드리프트 | High | 복구 직후 폴 1회 강제 수행 + 서버 응답으로 LED 재설정 |
| ESP 메모리 고갈 (ArduinoJson + HTTPClient) | Medium | `StaticJsonDocument<512>` 상한, 요청 후 즉시 `http.end()` |
| 인터럽트 핸들러 중 `Serial.println` 크래시 | High | 핸들러는 플래그만 set, 로그는 메인 루프에서 출력 |
| D8 부팅 핀 오동작 | Low | 외부 풀다운 현행 유지 확인, 필요 시 LED 재배치 |
| 서버-클라이언트 state 스키마 불일치 | Medium | state 빌더 helper + 통합 테스트(curl 시뮬)로 계약 고정 |
| `ICACHE_RAM_ATTR` deprecated 경고 | Low | `IRAM_ATTR`로 교체 |

---

## 8. Dependencies

- `iot_relay_server` 가 기동 중 (`docker compose up`) 이고 Postgres 마이그레이션 완료
- `iot-manual-control` 서버·프론트 부분 배포 완료
- Arduino IDE 2.x + ESP8266 코어 3.x + 라이브러리: `ESP8266WiFi`, `ESP8266HTTPClient`, `ArduinoJson(6.x)`, `DHT` (DHT sensor library)
- 네트워크: ESP8266 → 퍼블릭 호스트 `iot.lilpa.moe` 접근 가능

---

## 9. Implementation Phases

| Phase | Deliverable | 검증 방법 |
|-------|-------------|-----------|
| P1. Contract Lock | 서버 API 응답 형식 확정 + state 스키마 문서화 | `curl` 시나리오 체크리스트 통과 |
| P2. Firmware Refactor | `.ino` 리라이트 (로컬 HTTP 서버 제거, 폴링 루프 추가) | 컴파일 성공 + 시리얼 로그 정상 |
| P3. 단방향 검증 (서버→ESP) | 프론트 토글로 3종 LED 점/소등 확인 | 육안 + 서버 로그 |
| P4. 단방향 검증 (ESP→서버) | 3개 버튼 눌러 프론트 토글 자동 반영 확인 | SSE 이벤트 + UI |
| P5. 교차 시나리오 | AI override + 수동 버튼 + 잠금 흐름 동시 검증 | `iot-manual-control` 시나리오 재사용 |
| P6. 스트레스 | 24h 구동 + WiFi 재부팅 2회 | 시리얼 로그 분석 |

---

## 10. Open Questions

1. 관수 LED는 `irrigation.active`를 미러링하는데, 서버 AI 규칙이 `valve_open`을 직접 세팅하는 경우 `active` 계산이 올바른지 재확인 필요.
2. 폴링 응답이 `{}`(빈 큐)인 경우 LED를 현 상태로 유지할지, 서버 `/control/state`를 주기적으로 pull하여 재동기화할지 — Design에서 결정.
3. ESP8266 펌웨어 버전을 `device_id` 또는 별도 필드로 서버에 보고할 필요가 있는지 (관측성 확장).
4. 버튼 1회 누름의 의미: "토글"인가 "ON 요청"인가 — 현 .ino는 토글. Design에서 명세 확정 필요.

---

## 11. Out-of-Scope (명시)

- 관수 제어용 버튼 하드웨어 추가
- 조도/온습도 기반 로컬 폴백 제어 (ESP 단독 판단)
- ESP Mesh / 다중 디바이스 운용
- 펌웨어 OTA, 비밀정보(wifi pw) 외부 주입
