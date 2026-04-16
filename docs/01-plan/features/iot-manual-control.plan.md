# IoT Manual Control Planning Document

> **Summary**: ESP8266 물리 버튼 + 프론트엔드 UI를 통한 양방향 수동 제어 시스템. LED 상태가 프론트엔드와 실시간 동기화.
>
> **Project**: FarmOS - IoT Manual Control
> **Version**: 0.1.0
> **Author**: clover0309
> **Date**: 2026-04-16
> **Status**: Draft
> **Prerequisites**: IoT Relay Server 정상 동작 (iot.lilpa.moe:9000), ESP8266 센서 데이터 수신 정상

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 IoT 시스템은 센서 모니터링만 가능하고, AI Agent의 가상 제어 상태 표시만 있을 뿐 실제 하드웨어를 수동으로 조작하거나 물리 버튼으로 제어하는 기능이 없다. |
| **Solution** | 프론트엔드에 4대 제어(환기/관수/조명/차광) 수동 조작 UI 추가 + ESP8266에 물리 버튼과 LED를 추가하여 양방향 제어 구현. Relay Server가 중계 허브 역할. |
| **Function/UX Effect** | 대시보드에서 슬라이더/토글로 직접 제어, ESP8266 버튼으로 물리적 토글, LED 상태가 양쪽에 실시간 반영되어 직관적인 농장 제어 UX 제공. |
| **Core Value** | 1인 농업인이 PC 대시보드 또는 현장 버튼 모두에서 즉시 제어 가능한 통합 제어 경험. 자동/수동 제어의 유기적 전환. |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 센서 모니터링만 가능한 IoT 시스템에 실제 수동 제어 + 물리 버튼 제어를 추가하여 양방향 하드웨어 연동 달성 |
| **WHO** | FarmOS 사용자 (1인 농업인), 대시보드에서 원격 제어 + 현장에서 버튼 제어 |
| **RISK** | ESP8266의 HTTP-only 통신 제약 (TLS 미지원), 폴링 지연 (최대 수 초), Relay Server 코드 변경 시 N100 재배포 필요 |
| **SUCCESS** | 프론트엔드 토글 -> 5초 내 ESP8266 LED 반응, ESP8266 버튼 -> 2초 내 프론트엔드 상태 반영, 4대 제어 항목 모두 양방향 동작 |
| **SCOPE** | Phase 1: 환기 -> Phase 2: 관수/양액 -> Phase 3: 조명 -> Phase 4: 차광/보온 (순차 구현, 각 단계 사용자 테스트 통과 후 진행) |

---

## 하드웨어 현황 (Critical Constraint)

> **현재 ESP8266에는 DHT11(D4) + KY-018 LDR(A0)만 연결되어 있습니다.**
> **버튼/LED 회로는 미구성 상태이며, 추후 브레드보드에서 구성 예정입니다.**

이에 따라 **Software-First 전략**을 채택합니다:
1. Relay Server API + Frontend UI + 시뮬레이션 모드를 먼저 구현
2. 프론트엔드 시뮬레이션 모드로 양방향 흐름을 검증
3. 회로 구성 후 ESP8266 펌웨어에서 LED/버튼 핀을 활성화

---

## 1. Overview

### 1.1 Purpose

FarmOS IoT 시스템에 **수동 제어 기능**을 추가하여 사용자가 프론트엔드 대시보드와 ESP8266 물리 버튼 두 경로로 4대 제어 항목(환기/관수/조명/차광)을 직접 조작하고, 제어 상태가 양방향으로 실시간 동기화되는 시스템을 구축한다.

### 1.2 Background

- **현재 상태**: 센서 4종 모니터링(온도, 습도, 조도, 토양수분 가상계산) + AI Agent 가상 제어 상태 표시만 구현
- **수동 관수 트리거**만 존재 (`POST /api/v1/irrigation/trigger`), 이마저도 이벤트 기록용이며 하드웨어와 연동되지 않음
- AI Agent는 가상 제어 상태만 표시 (실제 하드웨어 제어 없음, "가상 제어" 배지로 표시)
- ESP8266은 현재 센서 데이터 전송(HTTP POST, 30초 간격)만 수행하는 단방향 디바이스
- **요구**: 프론트엔드 UI 제어 + ESP8266 물리 버튼 제어 + LED 양방향 동기화

### 1.3 Related Documents

- IoT Relay Server 계획: `docs/iot-relay-server-plan.md`
- IoT AI Agent Automation 계획: `docs/01-plan/features/iot-ai-agent-automation.plan.md`
- ESP8266 작업 목록: `docs/esp8266-todo.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] 프론트엔드 수동 제어 UI (4대 제어 항목: 환기/관수/조명/차광)
- [ ] ESP8266 물리 버튼 추가 + 버튼 이벤트를 Relay Server로 전송
- [ ] ESP8266 LED 출력 (제어 상태 시각화)
- [ ] Relay Server에 제어 명령 저장/조회/큐잉 API 추가
- [ ] ESP8266 -> Relay Server -> Frontend (SSE) 상태 동기화 (버튼 -> LED -> 프론트엔드)
- [ ] Frontend -> Relay Server -> ESP8266 (폴링) 명령 전달 (프론트엔드 -> LED)
- [ ] 환기 -> 관수 -> 조명 -> 차광 순서 순차 구현

### 2.2 Out of Scope

- 실제 모터/밸브/보광등/차광막 하드웨어 연동 (LED로 시뮬레이션)
- AI Agent의 자동 제어 연동 (이번 피처는 수동 제어에 집중)
- TLS/HTTPS 통신 (ESP8266 하드웨어 제약)
- 로컬 Backend 서버 변경 (Relay Server에서 제어 명령 관리)
- 다중 ESP8266 디바이스 지원

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 프론트엔드에서 환기 제어(창문 개폐율 슬라이더, 팬 속도 조절) | High | Pending |
| FR-02 | 프론트엔드에서 관수 제어(밸브 열림/닫힘 토글) | High | Pending |
| FR-03 | 프론트엔드에서 조명 제어(ON/OFF 토글, 밝기 슬라이더) | High | Pending |
| FR-04 | 프론트엔드에서 차광/보온 제어(차광막 %, 보온 % 슬라이더) | High | Pending |
| FR-05 | ESP8266에 물리 버튼 추가, 버튼으로 제어 항목 토글 | High | Pending |
| FR-06 | ESP8266 버튼 누르면 LED ON/OFF, 해당 상태를 Relay Server로 전송 | High | Pending |
| FR-07 | Relay Server가 ESP8266 상태를 SSE로 프론트엔드에 브로드캐스트 | High | Pending |
| FR-08 | 프론트엔드 제어 명령 -> Relay Server -> ESP8266이 폴링하여 수신 | High | Pending |
| FR-09 | ESP8266이 폴링으로 받은 명령에 따라 LED 상태 변경 | High | Pending |
| FR-10 | 제어 명령 이력 저장 및 조회 | Medium | Pending |
| FR-11 | 수동 제어와 AI Agent 자동 제어 상태 구분 표시 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Latency (Frontend -> ESP8266) | 프론트엔드 명령 후 ESP8266 LED 반응 5초 이내 | ESP8266 폴링 주기(2~3초) + 네트워크 왕복 시간 측정 |
| Latency (ESP8266 -> Frontend) | 버튼 누름 후 프론트엔드 상태 반영 2초 이내 | SSE 이벤트 수신 타이밍 측정 |
| Reliability | ESP8266 WiFi 끊김 시 자동 재연결, 명령 유실 방지 | 네트워크 차단 후 복구 테스트 |
| Compatibility | ESP8266 (NodeMCU v1.0), Arduino IDE 호환 | 기존 핀 배치 유지, 추가 핀 사용 |
| Scalability | Relay Server 인메모리 명령 큐 1000건 제한 | 메모리 사용량 모니터링 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 프론트엔드에서 환기/관수/조명/차광 4개 제어 UI 동작
- [ ] ESP8266 물리 버튼 누르면 LED 토글 + Relay Server에 상태 전송
- [ ] Relay Server -> SSE -> 프론트엔드에 버튼 상태 실시간 반영
- [ ] 프론트엔드 제어 명령 -> Relay Server -> ESP8266 폴링 -> LED 반응
- [ ] 양방향 동기화: 프론트엔드 상태와 ESP8266 LED 상태 일치
- [ ] 각 제어 항목별 사용자 실 테스트 통과

### 4.2 Quality Criteria

- [ ] ESP8266 폴링 지연 5초 이내
- [ ] SSE 이벤트 전달 2초 이내
- [ ] WiFi 재연결 후 상태 정합성 유지
- [ ] Relay Server 재시작 후 마지막 제어 상태 복원

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| ESP8266 폴링 지연으로 프론트엔드-LED 상태 불일치 | Medium | High | 폴링 주기 2~3초로 설정, 프론트엔드에 "명령 전송 중..." 상태 표시 |
| ESP8266 메모리 부족 (HTTP 서버 + 클라이언트 동시 운영) | High | Medium | HTTP 서버 대신 폴링 방식 채택 (ESP8266이 주기적으로 명령 조회) |
| Relay Server 재시작 시 제어 상태 초기화 | Medium | Medium | 마지막 제어 상태를 파일/JSON으로 영속화 |
| N100 서버 코드 변경 시 재배포 필요 | Medium | High | 변경 범위 최소화, 명확한 재배포 안내 절차 |
| WiFi 불안정으로 ESP8266 연결 끊김 | Medium | Medium | 자동 재연결 로직, 연결 끊김 시 마지막 상태 유지 |
| 버튼 디바운싱 미처리로 중복 명령 전송 | Low | Medium | 하드웨어/소프트웨어 디바운싱 200ms 적용 |
| ESP8266 핀 부족 (센서 + 버튼 + LED) | Low | Low | NodeMCU 사용 가능 핀 확인: D1~D8 중 D4(DHT11), A0(LDR) 외 6개 여유 |

---

## 6. Current System Analysis

### 6.1 현재 아키텍처

```
ESP8266 (DHT11 + KY-018 LDR)
    | HTTP POST /api/v1/sensors (30초 간격, X-API-Key: farmos-iot-default-key)
    v
IoT Relay Server (iot.lilpa.moe:9000, FastAPI, Docker on N100)
    |- SSE broadcast -> Frontend (sensor, alert, irrigation events)
    |- REST API -> Frontend (latest, history, alerts, irrigation/events)
    |- AI Agent API -> Frontend (status, decisions, override, crop-profile)
    v
Frontend (React + Vite, localhost:5173)
    |- useSensorData.ts: SSE + 60초 전체 동기화
    |- useAIAgent.ts: 30초 폴링
    |- IoTDashboardPage.tsx: 센서 카드 + 차트 + 관수 이력 + 알림
    |- AIAgentPanel.tsx: AI 제어 상태 표시 (가상 제어)
```

### 6.2 현재 통신 흐름 (단방향)

```
ESP8266 ----POST----> Relay Server ----SSE----> Frontend
                                   <---GET----- Frontend (폴링/직접 요청)
```

- ESP8266은 **전송만** 수행 (수신 기능 없음)
- Relay Server -> ESP8266 방향 통신 경로 없음
- Frontend -> Relay Server -> ESP8266 명령 전달 경로 없음

### 6.3 ESP8266 현재 핀 사용

| 핀 | 용도 | 비고 |
|----|------|------|
| D4 (GPIO2) | DHT11 센서 | 온도/습도 |
| A0 | KY-018 LDR | 조도 (아날로그 입력) |
| - | WiFi (내장) | HTTP POST 전송 |

**사용 가능 핀**: D0, D1, D2, D3, D5, D6, D7, D8 (8개)

### 6.4 Relay Server 현재 API (iot.lilpa.moe:9000)

| Method | Path | 인증 | 용도 |
|--------|------|------|------|
| POST | `/api/v1/sensors` | X-API-Key | ESP8266 센서 수신 |
| GET | `/api/v1/sensors/latest` | - | 최신 센서값 |
| GET | `/api/v1/sensors/history` | - | 시계열 데이터 |
| GET | `/api/v1/sensors/alerts` | - | 알림 목록 |
| GET | `/api/v1/sensors/stream` | - | SSE 스트림 |
| POST | `/api/v1/irrigation/trigger` | - | 수동 관수 |
| GET | `/api/v1/irrigation/events` | - | 관수 이력 |
| GET | `/api/v1/ai-agent/status` | - | AI Agent 상태 |
| POST | `/api/v1/ai-agent/toggle` | - | AI Agent ON/OFF |
| PUT | `/api/v1/ai-agent/crop-profile` | - | 작물 프로필 수정 |
| POST | `/api/v1/ai-agent/override` | - | 수동 오버라이드 |

---

## 7. Communication Protocol Design

### 7.1 목표 아키텍처 (양방향)

```
                    ┌──────────────────────────────────────────┐
                    │     IoT Relay Server (iot.lilpa.moe)      │
                    │                                          │
   ESP8266 -------->│  POST /sensors (센서 데이터)              │------> SSE -------> Frontend
   (30초 간격)       │  POST /control/report (버튼/LED 상태)    │  (sensor event)
                    │                                          │
   ESP8266 <------->│  GET  /control/commands (폴링, 2~3초)    │<------ POST -------- Frontend
   (폴링 수신)       │  POST /control (프론트엔드 명령)         │  (제어 명령 전송)
                    │                                          │
                    │  [인메모리 제어 상태 저장소]               │------> SSE -------> Frontend
                    │  - pending_commands queue                │  (control event)
                    │  - current_control_state                 │
                    └──────────────────────────────────────────┘
```

### 7.2 통신 프로토콜 상세

#### 7.2.1 Frontend -> ESP8266 (프론트엔드 제어 명령)

```
1. Frontend: POST /api/v1/control
   Body: { "control_type": "ventilation", "action": { "window_open_pct": 70 }, "source": "manual" }

2. Relay Server: 명령을 pending_commands 큐에 저장 + current_control_state 업데이트

3. Relay Server: SSE로 "control" 이벤트 브로드캐스트 (프론트엔드 즉시 반영)

4. ESP8266: GET /api/v1/control/commands (2~3초 폴링)
   Response: { "commands": [{ "control_type": "ventilation", "action": { "window_open_pct": 70 } }] }

5. ESP8266: 명령 수신 후 LED 상태 변경 + POST /api/v1/control/ack (수신 확인)
```

#### 7.2.2 ESP8266 -> Frontend (버튼 제어)

```
1. ESP8266: 물리 버튼 누름 (디바운싱 200ms)

2. ESP8266: LED 상태 즉시 토글

3. ESP8266: POST /api/v1/control/report
   Body: { "device_id": "esp8266-01", "control_type": "ventilation", "state": { "led_on": true, "window_open_pct": 100 }, "source": "button" }

4. Relay Server: current_control_state 업데이트

5. Relay Server: SSE "control" 이벤트 브로드캐스트 -> Frontend 즉시 반영
```

### 7.3 제어 상태 데이터 모델

```python
# Relay Server: 인메모리 제어 상태
control_state = {
    "ventilation": {
        "window_open_pct": 0,    # 0~100
        "fan_speed": 0,          # RPM
        "led_on": False,         # ESP8266 LED 상태
        "source": "manual",      # manual | button | ai
        "updated_at": "ISO8601"
    },
    "irrigation": {
        "valve_open": False,
        "led_on": False,
        "source": "manual",
        "updated_at": "ISO8601"
    },
    "lighting": {
        "on": False,
        "brightness_pct": 0,
        "led_on": False,
        "source": "manual",
        "updated_at": "ISO8601"
    },
    "shading": {
        "shade_pct": 0,
        "insulation_pct": 0,
        "led_on": False,
        "source": "manual",
        "updated_at": "ISO8601"
    }
}

# Pending commands queue (ESP8266이 폴링으로 가져감)
pending_commands = deque(maxlen=100)
```

### 7.4 Relay Server 신규 API

| Method | Path | 인증 | 용도 |
|--------|------|------|------|
| POST | `/api/v1/control` | - | 프론트엔드 -> 제어 명령 전송 |
| GET | `/api/v1/control/state` | - | 현재 전체 제어 상태 조회 |
| GET | `/api/v1/control/commands` | X-API-Key | ESP8266 -> 대기 명령 폴링 |
| POST | `/api/v1/control/report` | X-API-Key | ESP8266 -> 버튼/LED 상태 보고 |
| POST | `/api/v1/control/ack` | X-API-Key | ESP8266 -> 명령 수신 확인 |

### 7.5 SSE 이벤트 확장

기존 SSE 이벤트 타입에 `control` 이벤트 추가:

```
event: control
data: {
    "control_type": "ventilation",
    "state": { "window_open_pct": 70, "fan_speed": 0, "led_on": true },
    "source": "button",
    "timestamp": "2026-04-16T14:30:00Z"
}
```

### 7.6 ESP8266 폴링 시퀀스

```
기존 loop (30초 간격):
    1. 센서 읽기 -> POST /sensors

신규 loop (2~3초 간격, 별도 타이밍):
    1. GET /control/commands
    2. 새 명령 있으면 -> LED 상태 변경 + POST /control/ack
    3. 버튼 상태 확인 (인터럽트 플래그)
    4. 버튼 눌렸으면 -> LED 토글 + POST /control/report
```

---

## 8. ESP8266 Hardware Design

### 8.1 추가 하드웨어

| 부품 | 수량 | 용도 | 비고 |
|------|------|------|------|
| 택트 스위치 (Tact Switch) | 1~4개 | 제어 항목 토글 | Phase별 1개씩 추가 |
| LED | 1~4개 | 제어 상태 표시 | 각 제어 항목별 1개 |
| 저항 (220ohm) | 1~4개 | LED 전류 제한 | LED당 1개 |
| 저항 (10Kohm) | 1~4개 | 버튼 풀다운 | 버튼당 1개 |

### 8.2 핀 배정 계획

| 핀 | 기존/신규 | 용도 | Phase |
|----|----------|------|-------|
| D4 | 기존 | DHT11 센서 | - |
| A0 | 기존 | KY-018 LDR | - |
| D1 | 신규 | 환기 LED | Phase 1 |
| D2 | 신규 | 환기 버튼 | Phase 1 |
| D5 | 신규 | 관수 LED | Phase 2 |
| D6 | 신규 | 관수 버튼 | Phase 2 |
| D7 | 신규 | 조명 LED | Phase 3 |
| D8 | 신규 | 조명 버튼 | Phase 3 |
| D3 | 신규 | 차광 LED | Phase 4 |
| D0 | 신규 | 차광 버튼 | Phase 4 |

### 8.3 버튼 디바운싱

```cpp
// 소프트웨어 디바운싱 (인터럽트 + millis)
#define DEBOUNCE_MS 200

volatile bool buttonPressed = false;
unsigned long lastButtonTime = 0;

ICACHE_RAM_ATTR void handleButtonISR() {
    if (millis() - lastButtonTime > DEBOUNCE_MS) {
        buttonPressed = true;
        lastButtonTime = millis();
    }
}
```

---

## 9. Implementation Phases

### Phase 1: 환기 (Ventilation) -- 기반 인프라 + 첫 번째 제어

**목표**: 전체 양방향 통신 인프라 구축 + 환기 제어 1건 완성

**Relay Server 변경**:
1. [ ] 제어 상태 인메모리 저장소 (`control_store.py`)
2. [ ] 제어 명령 API 엔드포인트 (`POST /control`, `GET /control/state`)
3. [ ] ESP8266 폴링 엔드포인트 (`GET /control/commands`, `POST /control/ack`)
4. [ ] ESP8266 상태 보고 엔드포인트 (`POST /control/report`)
5. [ ] SSE에 `control` 이벤트 타입 추가

**ESP8266 변경**:
6. [ ] 환기 버튼 (D2) + LED (D1) 하드웨어 배선
7. [ ] 버튼 인터럽트 + 디바운싱 구현
8. [ ] LED 제어 로직 (토글)
9. [ ] 폴링 루프 (2~3초 간격, GET /control/commands)
10. [ ] 명령 수신 시 LED 상태 변경 + ACK 전송
11. [ ] 버튼 누름 시 POST /control/report

**Frontend 변경**:
12. [ ] `useManualControl` 훅 (제어 상태 관리 + SSE 수신)
13. [ ] 환기 제어 UI (창문 개폐율 슬라이더, 팬 속도)
14. [ ] SSE `control` 이벤트 수신 처리 (`useSensorData.ts` 확장)
15. [ ] 수동 제어 패널 컴포넌트 (`ManualControlPanel.tsx`)

**테스트 기준**:
- [T1-1] 프론트엔드에서 환기 ON -> ESP8266 LED 점등 (5초 이내)
- [T1-2] ESP8266 버튼 누름 -> LED 토글 -> 프론트엔드 상태 반영 (2초 이내)
- [T1-3] 창문 개폐율 슬라이더 조작 -> 값이 프론트엔드와 Relay Server에서 일치

### Phase 2: 관수/양액 (Irrigation)

**목표**: Phase 1 인프라 위에 관수 제어 추가

**ESP8266 변경**:
1. [ ] 관수 버튼 (D6) + LED (D5) 하드웨어 배선
2. [ ] 관수 버튼/LED 로직 추가

**Frontend 변경**:
3. [ ] 관수 제어 UI (밸브 열림/닫힘 토글)
4. [ ] `useManualControl` 훅에 관수 제어 추가
5. [ ] 기존 관수 이벤트와 수동 제어 이벤트 통합 표시

**Relay Server 변경**:
6. [ ] 관수 제어 상태 관리 추가

**테스트 기준**:
- [T2-1] 프론트엔드에서 밸브 열림 -> ESP8266 관수 LED 점등
- [T2-2] ESP8266 관수 버튼 -> LED 토글 -> 프론트엔드 밸브 상태 반영
- [T2-3] 관수 이벤트 이력에 수동 제어 기록 표시

### Phase 3: 조명 (Lighting)

**목표**: 조명 ON/OFF + 밝기 조절

**ESP8266 변경**:
1. [ ] 조명 버튼 (D8) + LED (D7) 하드웨어 배선
2. [ ] 조명 버튼/LED 로직 (PWM으로 밝기 시뮬레이션 가능)

**Frontend 변경**:
3. [ ] 조명 제어 UI (ON/OFF 토글 + 밝기 슬라이더)
4. [ ] `useManualControl` 훅에 조명 제어 추가

**Relay Server 변경**:
5. [ ] 조명 제어 상태 관리 추가

**테스트 기준**:
- [T3-1] 프론트엔드 조명 ON -> ESP8266 조명 LED 점등
- [T3-2] 밝기 조절 -> ESP8266 LED PWM 밝기 변화 (선택)
- [T3-3] ESP8266 조명 버튼 -> 프론트엔드 즉시 반영

### Phase 4: 차광/보온 (Shading)

**목표**: 차광막 %, 보온 % 제어

**ESP8266 변경**:
1. [ ] 차광 버튼 (D0) + LED (D3) 하드웨어 배선
2. [ ] 차광 버튼/LED 로직

**Frontend 변경**:
3. [ ] 차광/보온 제어 UI (차광막 % 슬라이더, 보온 % 슬라이더)
4. [ ] `useManualControl` 훅에 차광/보온 제어 추가

**Relay Server 변경**:
5. [ ] 차광/보온 제어 상태 관리 추가

**테스트 기준**:
- [T4-1] 프론트엔드 차광막 50% -> Relay Server 상태 업데이트 + ESP8266 LED 점등
- [T4-2] ESP8266 차광 버튼 -> 프론트엔드 즉시 반영
- [T4-3] 4대 제어 항목 모두 동시 동작, 상태 정합성 유지

---

## 10. Impact Analysis

### 10.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| Relay Server (iot.lilpa.moe:9000) | Server API | 제어 명령 API 5개 추가, SSE에 control 이벤트 추가 |
| ESP8266 펌웨어 (.ino) | Firmware | 버튼/LED 핀 추가, 폴링 루프 추가, 기존 센서 루프 유지 |
| Frontend useSensorData.ts | Hook | SSE control 이벤트 수신 추가 |
| Frontend IoTDashboardPage.tsx | Component | 수동 제어 패널 영역 추가 |
| Frontend types/index.ts | Types | ManualControlState, ControlCommand 타입 추가 |

### 10.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| Relay Server SSE | READ | `useSensorData.ts` -> EventSource | sensor/alert/irrigation 이벤트 유지, control 이벤트 추가 |
| Relay Server AI Agent API | READ | `useAIAgent.ts` -> fetch polling | 변경 없음 (AI Agent는 별도 상태) |
| ESP8266 센서 POST | WRITE | `.ino` -> HTTP POST /sensors | 30초 간격 유지, 별도 폴링 루프 추가 |
| Frontend AIAgentPanel | READ | `AIAgentPanel.tsx` | AI 가상 제어 표시 유지, 수동 제어와 UI 영역 분리 |

### 10.3 Verification

- [ ] 기존 센서 데이터 수집 흐름 (ESP8266 -> Relay -> SSE -> Frontend) 영향 없음
- [ ] AI Agent 상태/판단 API 영향 없음
- [ ] 관수 이벤트 API 하위 호환 유지
- [ ] 프론트엔드 기존 차트/알림 UI 영향 없음

---

## 11. Architecture Considerations

### 11.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites, portfolios | - |
| **Dynamic** | Feature-based modules, BaaS integration | Web apps with backend, SaaS MVPs | **Selected** |
| **Enterprise** | Strict layer separation, microservices | High-traffic systems | - |

### 11.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| ESP8266 -> Relay 양방향 통신 | (A) WebSocket / (B) ESP8266 HTTP Server / (C) 폴링 | **(C) 폴링** | ESP8266 메모리 제약 (WebSocket 라이브러리 무거움), HTTP 서버 병행 시 안정성 이슈. 폴링이 가장 안정적. |
| 제어 상태 저장 | (A) PostgreSQL / (B) Redis / (C) 인메모리 + 파일 백업 | **(C) 인메모리 + 파일** | Relay Server가 인메모리 기반, DB 의존 없음. 파일 백업으로 재시작 시 복구. |
| 프론트엔드 제어 수신 | (A) 폴링 / (B) SSE (기존 확장) / (C) WebSocket | **(B) SSE 확장** | 기존 SSE 인프라 활용. control 이벤트 타입 추가만으로 구현 가능. |
| 순차 구현 전략 | (A) 4개 동시 / (B) 환기 먼저 + 나머지 순차 | **(B) 순차** | 하드웨어 테스트가 필요하므로 1개씩 완성 후 검증. |
| ESP8266 폴링 주기 | (A) 1초 / (B) 2~3초 / (C) 5초 | **(B) 2~3초** | 응답성과 Relay Server 부하 균형. |
| 제어 명령 큐 방식 | (A) FIFO 큐 + ACK / (B) 최신 상태만 덮어쓰기 | **(B) 최신 상태 덮어쓰기** | ESP8266 폴링 간격 동안 여러 명령 시 최신 상태만 반영하면 충분. ACK로 수신 확인. |

### 11.3 Clean Architecture Approach

```
Selected Level: Dynamic

제어 흐름:
┌────────────────────────────────────────────────────────────────────┐
│ Frontend (React)                                                  │
│   src/modules/iot/ManualControlPanel.tsx  (UI)                    │
│   src/hooks/useManualControl.ts          (State + API)            │
│   src/hooks/useSensorData.ts             (SSE 확장)               │
│   src/types/index.ts                     (Types 추가)             │
├────────────────────────────────────────────────────────────────────┤
│ Relay Server (FastAPI, N100)                                      │
│   app/control_store.py     (인메모리 제어 상태 + 명령 큐)           │
│   app/control_routes.py    (제어 API 라우터)                       │
│   app/main.py              (라우터 등록 + SSE control 이벤트)       │
├────────────────────────────────────────────────────────────────────┤
│ ESP8266 (Arduino C++)                                             │
│   DH11_KY018_WiFi.ino     (기존 센서 루프 유지 + 폴링/버튼 루프)    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 12. Convention Prerequisites

### 12.1 Existing Project Conventions

- [x] TypeScript strict mode (Frontend)
- [x] React functional components + hooks pattern
- [x] Pydantic schemas (Backend/Relay Server)
- [x] FastAPI router pattern
- [ ] ESLint/Prettier 설정 (미확인)
- [x] ESP8266 Arduino IDE 환경

### 12.2 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `IOT_API_KEY` | ESP8266 인증 (기존) | Relay Server | Existing |
| `VITE_IOT_API_URL` | Relay Server URL (프론트엔드) | Frontend | May need |
| `CONTROL_STATE_FILE` | 제어 상태 백업 파일 경로 | Relay Server | New |

---

## 13. Deployment Notes

### 13.1 Relay Server (N100) 변경 시 절차

```
1. iot_relay_server/ 코드 수정 (로컬에서)
2. 수정된 코드를 N100 서버에 업로드 (scp / git push + pull)
3. N100에서 Docker 재빌드 + 재시작:
   cd iot_relay_server
   docker compose down
   docker compose up -d --build
4. 헬스체크: curl http://iot.lilpa.moe:9000/health
```

> **중요**: N100 서버 직접 조작 금지. 사용자에게 위 절차 안내 후 대기.

### 13.2 ESP8266 변경 시 절차

```
1. DH11_KY018_WiFi.ino 코드 수정
2. 브레드보드에 버튼/LED 배선 추가
3. Arduino IDE에서 컴파일 + 업로드
4. 시리얼 모니터로 동작 확인
```

### 13.3 Frontend 변경 시 절차

```
1. 코드 수정 (로컬)
2. npm run dev (자동 핫 리로드)
3. 브라우저에서 IoT 대시보드 확인
```

---

## 14. Testing Strategy

### 14.1 단위 테스트 (각 Phase)

| 대상 | 테스트 방법 | 도구 |
|------|-----------|------|
| Relay Server API | curl/httpie로 엔드포인트 호출 | Terminal |
| SSE 이벤트 | curl 스트리밍 수신 확인 | Terminal |
| ESP8266 폴링 | 시리얼 모니터 + Relay Server 로그 | Arduino IDE |
| Frontend UI | 브라우저 수동 테스트 | Chrome DevTools |

### 14.2 통합 테스트 (Phase별 완료 시)

```
시나리오 A: Frontend -> ESP8266
1. 프론트엔드에서 환기 ON 버튼 클릭
2. Relay Server에 POST /control 확인 (로그)
3. ESP8266이 GET /control/commands로 명령 수신 (시리얼 모니터)
4. ESP8266 LED 점등 확인 (실물)
5. ESP8266이 POST /control/ack 전송 확인

시나리오 B: ESP8266 -> Frontend
1. ESP8266 물리 버튼 누름
2. ESP8266 LED 토글 확인 (실물)
3. ESP8266이 POST /control/report 전송 (시리얼 모니터)
4. Relay Server SSE에 control 이벤트 발생 (curl 확인)
5. 프론트엔드 제어 상태 업데이트 확인 (브라우저)

시나리오 C: 동시성
1. 프론트엔드에서 환기 ON
2. 즉시 ESP8266 버튼으로 환기 OFF
3. 최종 상태가 프론트엔드와 ESP8266에서 일치하는지 확인
```

### 14.3 ESP8266 없이 사전 테스트

```bash
# Relay Server API 테스트 (curl)

# 1. 제어 명령 전송 (프론트엔드 시뮬레이션)
curl -X POST http://iot.lilpa.moe:9000/api/v1/control \
  -H "Content-Type: application/json" \
  -d '{"control_type":"ventilation","action":{"window_open_pct":70},"source":"manual"}'

# 2. 제어 상태 조회
curl http://iot.lilpa.moe:9000/api/v1/control/state

# 3. 대기 명령 조회 (ESP8266 시뮬레이션)
curl -H "X-API-Key: farmos-iot-default-key" \
  http://iot.lilpa.moe:9000/api/v1/control/commands

# 4. 버튼 상태 보고 (ESP8266 시뮬레이션)
curl -X POST http://iot.lilpa.moe:9000/api/v1/control/report \
  -H "Content-Type: application/json" \
  -H "X-API-Key: farmos-iot-default-key" \
  -d '{"device_id":"esp8266-01","control_type":"ventilation","state":{"led_on":true,"window_open_pct":100},"source":"button"}'

# 5. SSE 스트림 (control 이벤트 수신 확인)
curl -N http://iot.lilpa.moe:9000/api/v1/sensors/stream
```

---

## 15. Next Steps

1. [ ] Write design document (`iot-manual-control.design.md`) -- 3가지 설계안 비교
2. [ ] Relay Server `iot_relay_server/` 코드 확인 (N100에서 현재 버전 파악)
3. [ ] Phase 1 (환기) 구현 시작
4. [ ] Phase 1 사용자 테스트 통과 후 Phase 2 진행

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-16 | Initial draft | clover0309 |
