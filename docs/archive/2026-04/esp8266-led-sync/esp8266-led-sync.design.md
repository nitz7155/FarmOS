# ESP8266 LED Sync Design Document

> **Feature**: esp8266-led-sync
> **Architecture**: Option C — Pragmatic Balance (선택)
> **Plan Reference**: `docs/01-plan/features/esp8266-led-sync.plan.md`
> **Date**: 2026-04-21
> **Status**: Draft
> **Scope Note**: 본 문서는 펌웨어 측 구현만 포함. 서버(`iot_relay_server`)와 프론트엔드는 `iot-manual-control`로 완성되어 있다는 전제.

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 기존 `iot-manual-control` 설계의 ESP8266 단(Step 2)이 미구현 상태라 서버·프론트엔드만 완성된 상태의 반쪽 시스템을 끝내 닫기 위함 |
| **WHO** | FarmOS 1인 농업인 — 현장 버튼 3개(환기/조명/차광) + 대시보드 토글 + AI 자동화 3개 경로 사용 |
| **RISK** | ESP8266 메모리·스택 제약, 폴링 주기 vs 반응성 트레이드오프, WiFi 끊김 시 상태 불일치, 인터럽트-안전 로직 설계, D0/D2/D8 부팅 핀 주의 |
| **SUCCESS** | 프론트엔드 토글 → ≤ 5s LED 반응 / 물리 버튼 → ≤ 2s 프론트엔드 반영 / 24h 무재부팅 / 네트워크 회복 후 자동 재수렴 |
| **SCOPE** | In: 환기/조명/차광 3버튼 양방향 + 관수 LED 미러링. Out: 관수 버튼, MQTT/WS 전환, OTA |

---

## 1. Architecture Options

### Option A — Minimal Changes (최소 변경)
- 기존 `.ino`의 `sendToServer()`를 유지하되, `ESP8266WebServer(80)` 대신 서버 폴링으로 `/control`을 대체.
- `sensors` POST에 `actuators`도 그대로 동봉.
- 버튼 변경 시에도 `/api/v1/sensors`로만 전송, 서버 측에서 actuators를 해석하도록 별도 엔드포인트 추가.

**장점**: 변경 최소, 1시간 내 수정 가능.
**단점**: 서버 계약이 오염됨(`/sensors`에 제어 정보 혼재), 기존 `/control/*` API 무용화, iot-manual-control 설계와 모순.

### Option B — Clean Architecture (이상적 분리)
- ESP8266에 Command Pattern / State Machine 도입: `CommandPoller`, `ButtonReporter`, `LedController`, `WifiManager`, `HttpClientFacade` 5개 클래스 분리.
- 각 클래스에 단위 테스트(로컬 emulator) 작성.
- `ArduinoJson` + 스트림 파싱으로 메모리 최적화.
- OTA, mDNS 등 확장 포인트 미리 구축.

**장점**: 유지보수성 최상, 향후 OTA/MQTT 전환 용이, 테스트 가능성 높음.
**단점**: ESP8266 flash/heap 압박, 초기 구현 부담 크고 단일 기능에 과한 구조, 버그 유발 표면 증가.

### Option C — Pragmatic Balance (선택 ★)
- 기존 `.ino` 단일 파일 유지 + **로컬 HTTP 서버 제거** + **폴링 루프 추가**.
- 함수 단위 분리: `pollCommands()`, `reportButton(control_type, state)`, `applyCommand(ct, action)`, `ackCommands(...)`, `mirrorLeds(serverState)`.
- 비블로킹 타이머(`millis()`) + 인터럽트-안전 플래그로 단순 상태기 구현.
- 서버 `/control/*` 계약을 그대로 사용 (신규 엔드포인트 0개).
- 확장 여지는 함수 경계로만 남기고 클래스화는 유보.

**장점**: 중간 복잡도, ESP8266 리소스 안전, 기존 `iot-manual-control` 설계와 정합. 테스트/롤백 쉬움.
**단점**: OTA/MQTT 전환 시 일부 재작성 필요(수용 가능한 트레이드오프).

### 비교표

| 항목 | Option A | Option B | **Option C ★** |
|------|----------|----------|----------------|
| 구현 공수 | 0.5d | 3–5d | **1.5d** |
| 메모리(예상 free heap) | 22–25KB | 15–18KB | **20–22KB** |
| 기존 계약 재사용 | ✗ | ✓ | **✓** |
| 유지보수성 | 낮음 | 최상 | **중상** |
| 설계-구현 정합성 | 불일치 | 일치 | **일치** |
| 리스크 | 높음(계약 오염) | 중(초기 버그) | **낮음** |

**선택 사유**: (1) 서버/프론트가 이미 폴링 계약으로 배포되어 있고, (2) ESP8266 리소스 여유가 넉넉치 않으며, (3) 단일 개발자 운영이라 과도한 추상화는 부담. C가 iot-manual-control 설계의 "Step 2"와 가장 일관됨.

---

## 2. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                        Cloud (tunnel)                        │
│                                                              │
│   Frontend ──► POST /api/v1/control ──► control_store.py     │
│         ▲                                │                   │
│         │ SSE control                    ▼                   │
│         │                       pending_commands[ct]         │
│         │                                │                   │
│                                          ▼                   │
│   POST /api/v1/control/report ◄── control_state[ct]          │
│         ▲             │                  ▲                   │
│         │             │                  │                   │
└─────────┼─────────────┼──────────────────┼───────────────────┘
          │             │                  │
          │      (every 2s) GET /control/commands?device_id=
          │             │                  │
          │             │           (after apply) POST /control/ack
          │             ▼                  │
          │     ┌────────────────────┐     │
          │     │  ESP8266 main loop │     │
          │     │                    │     │
          │     │  ┌─ pollCommands ──┼─────┘
          │     │  │                 │
          │     │  ├─ applyCommand ──► updateLEDs()
          │     │  │
          │     │  ├─ checkButtons ─► reportButton() ──────────┐
          │     │  │      ▲                                    │
          │     │  │      │ ISR flags                          │
          │     │  │  BTN_FAN/LIGHT/SHADE (D7/D6/D3)           │
          │     │  │                                           │
          │     │  └─ sendSensors (30s, 제어정보 없음) ─────────┤
          │     └────────────────────┘                         │
          └────────────────────────────────────────────────────┘
                       (physical world)
                  LED: D1/D0/D2/D8
```

---

## 3. State Model

### 3.1 펌웨어 in-memory 상태

| 변수 | 타입 | 초기값 | 설명 |
|------|------|--------|------|
| `fanOn` | bool | false | 서버 `ventilation.active` 미러 |
| `lightOn` | bool | false | 서버 `lighting.on` 미러 |
| `shadeOn` | bool | false | 서버 `shading.shade_pct > 0` 미러 |
| `waterOn` | bool | false | 서버 `irrigation.active` 미러 (읽기 전용) |
| `lastPollMs` | uint32 | 0 | 마지막 폴링 시각 |
| `lastSensorMs` | uint32 | 0 | 마지막 센서 POST 시각 |
| `wifiLostMs` | uint32 | 0 | WiFi 끊김 시각, 복구 판단용 |
| ISR flags | `volatile bool` | false | `fanPressed`, `lightPressed`, `shadePressed` |

### 3.2 제어 상태 머신 (per control_type)

```
          ┌──────────┐  button press   ┌──────────┐
          │  Idle    │ ──────────────► │  Reporting│
          │ (LED=X)  │ ◄───────────────│           │
          └──────────┘   HTTP 200 ok   └──────────┘
               ▲                            │
               │                            ▼
               │                       ┌──────────┐
               │   ack complete        │ Reported │
               └──────────────────────►│(toggled) │
                                       └──────────┘

          ┌──────────┐   poll got cmd   ┌──────────┐
          │  Idle    │ ────────────────►│ Applying │
          │          │                  │          │
          └──────────┘                  └──────────┘
               ▲                             │
               │                             ▼
               │   ack 200                ┌──────────┐
               └─────────────────────────►│  Applied │
                                          └──────────┘
```

---

## 4. API Contract (서버 측 기존 계약 사용)

> 모든 요청은 `X-API-Key: farmos-iot-default-key` + `Bypass-Tunnel-Reminder: true` 헤더 포함.

### 4.1 `GET /api/v1/control/commands?device_id=esp8266-01`

**응답 (200)**:
```json
{
  "commands": {
    "ventilation": { "window_open_pct": 50, "fan_speed": 50, "timestamp": "..." },
    "lighting": { "on": true, "brightness_pct": 100, "timestamp": "..." }
  },
  "timestamp": "2026-04-21T10:00:00+00:00"
}
```

**응답 (빈 큐)**: `{ "commands": {}, "timestamp": "..." }`

**펌웨어 해석 규칙**:
- `commands`의 각 key(control_type)마다 LED 상태를 재계산:
  - `ventilation.active = (window_open_pct > 0 || fan_speed > 0)` → `fanOn`
  - `lighting.on` → `lightOn`
  - `shading.shade_pct > 0` → `shadeOn`
  - `irrigation.valve_open` or `active` → `waterOn`
- 명령을 적용한 control_type들을 모아 ack 호출.

### 4.2 `POST /api/v1/control/report`

**요청**:
```json
{
  "device_id": "esp8266-01",
  "control_type": "ventilation",
  "state": { "active": true, "fan_speed": 50, "window_open_pct": 50 },
  "source": "button"
}
```

**state 페이로드 규약 (버튼 토글 정책)**:

| control_type | state (토글 ON) | state (토글 OFF) |
|--------------|----------------|------------------|
| ventilation | `{ "active": true, "fan_speed": 50, "window_open_pct": 50 }` | `{ "active": false, "fan_speed": 0, "window_open_pct": 0 }` |
| lighting | `{ "on": true, "brightness_pct": 100 }` | `{ "on": false, "brightness_pct": 0 }` |
| shading | `{ "shade_pct": 100, "insulation_pct": 0 }` | `{ "shade_pct": 0, "insulation_pct": 0 }` |

> 서버 `update_control_state(source="button")`는 자동으로 `locked=true` 처리 → AI 규칙 덮어쓰기 방지.

### 4.3 `POST /api/v1/control/ack`

**요청**:
```json
{
  "device_id": "esp8266-01",
  "acknowledged_types": ["ventilation", "lighting"]
}
```

### 4.4 `POST /api/v1/sensors` (기존, actuators 제거)

**요청 (수정 후)**:
```json
{
  "device_id": "esp8266-01",
  "sensors": {
    "temperature": 22.5,
    "humidity": 65.3,
    "light_intensity": 42
  }
}
```

**변경점**: 기존 `.ino`의 `"actuators": {...}` 필드 **제거**. 센서와 제어 관심사 완전 분리.

---

## 5. Firmware File Structure

```
FarmOS/DH11_KY018_WiFi/
└── DH11_KY018_WiFi.ino      [수정]
```

단일 파일 유지 (Option C 결정). 함수 블록으로 논리 경계만 명시.

### 5.1 함수 트리 (수정 후)

```
setup()
  ├─ initLeds()
  ├─ initButtons()
  ├─ initInterrupts()
  └─ connectWifi()

loop()
  ├─ handleWifi()            // 재접속 모니터링
  ├─ handleButtons()         // ISR 플래그 → reportButton()
  ├─ tickPoll()              // 2s 주기: pollCommands() → applyCommands() → ackCommands()
  └─ tickSensors()           // 30s 주기: sendSensors()

Helpers:
  pollCommands() → JsonDocument
  applyCommands(JsonDocument&, collected_types[])
  ackCommands(collected_types[])
  reportButton(const char* ct, const char* toggle_state)
  buildButtonState(const char* ct, bool on, char* buf, size_t len)
  mirrorLeds()               // 로컬 상태 → 핀 출력
  sendSensors()
  httpGet(url) / httpPostJson(url, body) — 공통 래퍼
```

---

## 6. Firmware Pseudocode (핵심 발췌)

### 6.1 전역 / 상수

```cpp
// Design Ref: §3.1 — in-memory state
#define POLL_INTERVAL_MS    2000UL
#define SENSOR_INTERVAL_MS  30000UL
#define HTTP_TIMEOUT_MS     5000
#define DEVICE_ID           "esp8266-01"
#define API_KEY             "farmos-iot-default-key"
#define HOST                "http://iot.lilpa.moe"

volatile bool fanPressed = false;
volatile bool lightPressed = false;
volatile bool shadePressed = false;

bool fanOn = false, lightOn = false, shadeOn = false, waterOn = false;
unsigned long lastPollMs = 0, lastSensorMs = 0;
```

### 6.2 setup() — 로컬 웹서버 **제거**

```cpp
void setup() {
  Serial.begin(9600);
  dht.begin();
  initLeds();
  initButtons();
  attachInterrupt(digitalPinToInterrupt(BTN_FAN),   onFanBtn,   FALLING);
  attachInterrupt(digitalPinToInterrupt(BTN_LIGHT), onLightBtn, FALLING);
  attachInterrupt(digitalPinToInterrupt(BTN_SHADE), onShadeBtn, FALLING);
  connectWifi();
  // NOTE: 로컬 ESP8266WebServer(80) 생성/등록 코드 제거됨.
  // 프론트엔드는 서버 /api/v1/control 경유로만 제어한다.
  Serial.println(F("[BOOT] polling mode ready"));
}
```

### 6.3 loop() — 비블로킹 스케줄러

```cpp
void loop() {
  handleWifi();
  handleButtons();

  unsigned long now = millis();
  if (now - lastPollMs >= POLL_INTERVAL_MS) {
    lastPollMs = now;
    tickPoll();
  }
  if (now - lastSensorMs >= SENSOR_INTERVAL_MS) {
    lastSensorMs = now;
    sendSensors();
  }
}
```

### 6.4 tickPoll() — 명령 수신 → 적용 → ack

```cpp
void tickPoll() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  String url = String(HOST) + "/api/v1/control/commands?device_id=" DEVICE_ID;
  http.begin(wificlient, url);
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("Bypass-Tunnel-Reminder", "true");

  int code = http.GET();
  if (code != 200) { Serial.printf("[POLL] HTTP %d\n", code); http.end(); return; }

  String body = http.getString();
  http.end();

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) { Serial.printf("[POLL] JSON err %s\n", err.c_str()); return; }

  JsonObject cmds = doc["commands"];
  if (cmds.isNull() || cmds.size() == 0) return;

  String acks;  // "ventilation,lighting"
  for (JsonPair kv : cmds) {
    const char* ct = kv.key().c_str();
    JsonObject a = kv.value().as<JsonObject>();
    applyCommand(ct, a);
    if (acks.length()) acks += ",";
    acks += ct;
  }
  mirrorLeds();
  ackCommands(acks);
}
```

### 6.5 applyCommand() — control_type별 매핑

```cpp
// Design Ref: §4.1 — 응답 해석 규칙
void applyCommand(const char* ct, JsonObject& a) {
  if (strcmp(ct, "ventilation") == 0) {
    int fs  = a["fan_speed"]       | -1;
    int wop = a["window_open_pct"] | -1;
    if (fs >= 0 || wop >= 0)
      fanOn = ((fs > 0) || (wop > 0));
    else if (a.containsKey("active"))
      fanOn = a["active"] | false;
  } else if (strcmp(ct, "lighting") == 0) {
    if (a.containsKey("on"))              lightOn = a["on"] | false;
    else if (a.containsKey("brightness_pct")) lightOn = (a["brightness_pct"] | 0) > 0;
  } else if (strcmp(ct, "shading") == 0) {
    if (a.containsKey("shade_pct"))       shadeOn = (a["shade_pct"] | 0) > 0;
  } else if (strcmp(ct, "irrigation") == 0) {
    if (a.containsKey("valve_open"))      waterOn = a["valve_open"] | false;
    else if (a.containsKey("active"))     waterOn = a["active"] | false;
  }
  // 그 외 control_type은 무시 (FR-02)
}
```

### 6.6 handleButtons() + reportButton()

```cpp
void handleButtons() {
  static unsigned long lastBtnMs = 0;
  if (millis() - lastBtnMs < 200) return;   // 소프트웨어 디바운스 (FR-11)

  if (fanPressed)   { fanPressed = false;   fanOn = !fanOn;     reportButton("ventilation", fanOn);   mirrorLeds(); lastBtnMs = millis(); }
  if (lightPressed) { lightPressed = false; lightOn = !lightOn; reportButton("lighting", lightOn);    mirrorLeds(); lastBtnMs = millis(); }
  if (shadePressed) { shadePressed = false; shadeOn = !shadeOn; reportButton("shading", shadeOn);     mirrorLeds(); lastBtnMs = millis(); }
}

void reportButton(const char* ct, bool on) {
  // Design Ref: §4.2 — state 페이로드 규약
  char state[96];
  if      (strcmp(ct, "ventilation") == 0) snprintf(state, sizeof(state),
      "{\"active\":%s,\"fan_speed\":%d,\"window_open_pct\":%d}", on?"true":"false", on?50:0, on?50:0);
  else if (strcmp(ct, "lighting") == 0)    snprintf(state, sizeof(state),
      "{\"on\":%s,\"brightness_pct\":%d}", on?"true":"false", on?100:0);
  else if (strcmp(ct, "shading") == 0)     snprintf(state, sizeof(state),
      "{\"shade_pct\":%d,\"insulation_pct\":0}", on?100:0);
  else return;

  char body[192];
  snprintf(body, sizeof(body),
    "{\"device_id\":\"" DEVICE_ID "\",\"control_type\":\"%s\",\"state\":%s,\"source\":\"button\"}",
    ct, state);
  httpPostJson("/api/v1/control/report", body);
  Serial.printf("[BTN] %s -> %s\n", ct, on?"ON":"OFF");
}
```

### 6.7 ackCommands() + mirrorLeds()

```cpp
void ackCommands(const String& csv) {
  // csv: "ventilation,lighting" -> JSON array
  String arr = "[";
  int start = 0;
  while (start < (int)csv.length()) {
    int comma = csv.indexOf(',', start);
    if (comma < 0) comma = csv.length();
    if (arr.length() > 1) arr += ",";
    arr += "\"" + csv.substring(start, comma) + "\"";
    start = comma + 1;
  }
  arr += "]";

  String body = String("{\"device_id\":\"" DEVICE_ID "\",\"acknowledged_types\":") + arr + "}";
  httpPostJson("/api/v1/control/ack", body.c_str());
}

void mirrorLeds() {
  digitalWrite(LED_FAN,   fanOn   ? HIGH : LOW);
  digitalWrite(LED_WATER, waterOn ? LOW  : HIGH);   // 내장 LED 반전
  digitalWrite(LED_LIGHT, lightOn ? HIGH : LOW);
  digitalWrite(LED_SHADE, shadeOn ? HIGH : LOW);
}
```

### 6.8 handleWifi() — 끊김 감지·재접속

```cpp
void handleWifi() {
  static bool wasConnected = true;
  bool now = (WiFi.status() == WL_CONNECTED);
  if (now && !wasConnected) {
    Serial.println(F("[WIFI] reconnected -> force poll"));
    lastPollMs = 0;         // 즉시 1회 폴 (FR-09)
  }
  if (!now) {
    WiFi.reconnect();
    delay(1000);
  }
  wasConnected = now;
}
```

### 6.9 ISR — IRAM_ATTR 마이그레이션

```cpp
IRAM_ATTR void onFanBtn()   { fanPressed = true; }
IRAM_ATTR void onLightBtn() { lightPressed = true; }
IRAM_ATTR void onShadeBtn() { shadePressed = true; }
```

---

## 7. Sequence Diagrams

### 7.1 프론트엔드 토글 → LED 점등

```
Frontend          RelayServer           ESP8266            LED
   │ toggle ON      │                      │                 │
   │───POST /control│                      │                 │
   │   (ventilation)│                      │                 │
   │◄──200 ok───────│                      │                 │
   │                │ pending[ventilation] │                 │
   │                │ state.active=true    │                 │
   │                │ SSE: control event   │                 │
   │◄──event────────│                      │                 │
   │                │          (≤ 2s poll) │                 │
   │                │◄──GET /commands──────│                 │
   │                │──{"ventilation":...}─►                 │
   │                │                      │ applyCommand    │
   │                │                      │ mirrorLeds ────►│ D1 HIGH
   │                │◄──POST /ack──────────│                 │
   │                │──200 ok──────────────►                 │
```

### 7.2 물리 버튼 누름 → 프론트 UI 반영

```
User        ESP8266                  RelayServer         Frontend
  │ press    │                           │                  │
  │────────► │ ISR: fanPressed=true      │                  │
  │          │ loop: fanOn=!fanOn        │                  │
  │          │ mirrorLeds  (D1 HIGH)     │                  │
  │          │──POST /control/report────►│                  │
  │          │◄─200 ok───────────────────│                  │
  │          │                           │ state.active=true│
  │          │                           │ SSE control ────►│
  │          │                           │                  │ UI ON
```

### 7.3 WiFi 끊김 복구

```
ESP8266        WiFi AP
  │ poll fail │ (down)
  │   ..      │
  │ WiFi.reconnect()
  │──────────►│ (up)
  │◄──assoc───│
  │ handleWifi(): wasConnected flip
  │ lastPollMs=0 → 즉시 폴 1회
  │ applyCommand + mirrorLeds  (재수렴)
```

---

## 8. Test Plan

### 8.1 L1 — API 계약 (curl 단독)

| ID | 시나리오 | 검증 |
|----|----------|------|
| L1-1 | `GET /control/commands?device_id=esp8266-01` with/without X-API-Key | 200 / 403 |
| L1-2 | Frontend POST `/control` → 이후 폴 응답에 해당 ct 포함 | commands 키 존재 |
| L1-3 | ESP POST `/control/report` → `/control/state` 응답에 반영 + `locked=true` | state.source=="button" |
| L1-4 | ESP POST `/control/ack` 후 재폴 → 동일 ct 미포함 | commands 키 제거 |

### 8.2 L2 — 펌웨어 동작 (Serial + 육안)

| ID | 시나리오 | 기대 |
|----|----------|------|
| L2-1 | 프론트 "환기 ON" → 5초 내 D1 LED HIGH | LED 점등 |
| L2-2 | BTN_LIGHT 1회 push → 2초 내 프론트 UI "ON" | UI 반영 |
| L2-3 | BTN_FAN 연타(5회/1s) → 디바운스 작동, 최종 상태만 기록 | 서버 기록 1~2건 |
| L2-4 | AI override `{ lighting: on=true }` → D2 점등 | LED 점등 |
| L2-5 | 수동 버튼 후 AI 규칙 트리거 → `locked=true`로 덮어쓰기 안 됨 | LED 유지 |

### 8.3 L3 — 통합 (E2E)

| ID | 시나리오 | 기대 |
|----|----------|------|
| L3-1 | WiFi AP 재부팅 (20s down) → ESP 자동 재접속 후 LED 재수렴 | 프론트 상태와 일치 |
| L3-2 | `/api/v1/sensors` 페이로드에 `actuators` 없음 확인 | 서버 로그 검증 |
| L3-3 | 24h 연속 구동 | free heap ±1KB, 크래시 0회 |

### 8.4 L4 — 회귀

- iot-manual-control 기존 시나리오(프론트 단독) 정상 동작 유지
- AI Agent 센서 기반 규칙이 여전히 control_type별로 `source="ai"` 소스로 동작

---

## 9. Observability

Serial 로그 포맷:

```
[BOOT] polling mode ready
[WIFI] connected ip=192.168.x.x
[POLL] 200 ok: ventilation=on lighting=off
[BTN]  ventilation -> ON
[HTTP] POST /control/report 200
[ACK]  ventilation,lighting
[SENS] t=22.5 h=65.3 l=42%
[WIFI] lost -> reconnecting
[WIFI] reconnected -> force poll
```

서버 `control_history`에 source 기록이 남아 디버깅 용이.

---

## 10. Rollout Plan

| Phase | 작업 | 롤백 |
|-------|------|------|
| R1 | `.ino` 수정 후 브레드보드 단일 유닛에 flash | 기존 `.ino`로 재flash |
| R2 | curl 시뮬(`/control/commands`) 응답을 수작업 주입하여 각 control_type 매핑 확인 | 서버 재시작 |
| R3 | 프론트엔드 1인 테스트 (24h) | 펌웨어 downgrade |
| R4 | 실 농장 투입 | 수동 잠금 해제 + 기존 펌웨어로 복구 |

---

## 11. Implementation Guide

### 11.1 변경/신규 파일

| 파일 | 타입 | 대상 |
|------|------|------|
| `FarmOS/DH11_KY018_WiFi/DH11_KY018_WiFi.ino` | 수정 | 전체 리라이트 (§5,§6) |

> 서버/프론트는 본 설계에서 변경 없음. 단, 서버 `control_store.get_and_clear_pending(device_id)`는 현재 device_id를 인자로 받되 필터링하지 않으므로 향후 다중 디바이스 시 확장 여지로 표시.

### 11.2 의존성

- Arduino IDE 2.x
- ESP8266 Boards Manager 3.1.2+
- `ESP8266WiFi`, `ESP8266HTTPClient` (코어 제공)
- `ArduinoJson@^6.21.4`
- `DHT sensor library@^1.4.6`
- `Adafruit Unified Sensor@^1.1.14`

### 11.3 Session Guide (권장 세션 분할)

| Session | Module | Scope Key | 출력물 |
|---------|--------|-----------|--------|
| S1 | 전역 상수 + setup() 정리 + 웹서버 제거 | `module-bootstrap` | 컴파일 성공 |
| S2 | `tickPoll` + `applyCommand` + `ackCommands` | `module-poll` | `[POLL]` 로그 정상 |
| S3 | `handleButtons` + `reportButton` | `module-report` | 버튼 → 서버 반영 |
| S4 | `handleWifi` + `mirrorLeds` + 센서 페이로드 정리 | `module-glue` | E2E 통과 |
| S5 | 로그/디바운스/IRAM 마이그레이션 마감 | `module-polish` | 24h 스트레스 준비 |

사용 예: `/pdca do esp8266-led-sync --scope module-poll`

### 11.4 코드 주석 규약

핵심 분기마다:
```cpp
// Design Ref: §6.5 — applyCommand mapping
// Plan SC-1: 프론트 → LED ≤ 5s
```

---

## 12. Acceptance Checklist

- [ ] `ESP8266WebServer server(80)` 관련 코드 전부 제거
- [ ] `sendToServer()`(舊) 함수 제거 또는 `sendSensors()`로 이름 변경 + `actuators` 필드 삭제
- [ ] `tickPoll` 2s 주기로 로그 출력되는지 확인
- [ ] 3개 control_type 모두 프론트 → LED / 버튼 → 프론트 양방향 확인
- [ ] 관수 LED가 서버 `irrigation.active` 변경 시 자동 미러링
- [ ] `ICACHE_RAM_ATTR` → `IRAM_ATTR` 마이그레이션 완료
- [ ] WiFi 재접속 후 `[WIFI] reconnected -> force poll` 로그 확인
- [ ] curl로 L1 4종 시나리오 통과
- [ ] 24h 연속 구동 후 free heap 기록 제출

---

## 13. Open Decisions (확정)

| Plan Q | 결정 | 근거 |
|--------|------|------|
| Q1 (관수 active 계산) | 서버 `control_store._update_active_and_led()` 로직 신뢰, ESP는 `valve_open` 또는 `active` 키를 순서대로 읽음 | 서버가 SSoT |
| Q2 (빈 큐 시) | LED 현 상태 유지. 재수렴이 필요한 경우(WiFi 복구)만 `/control/state` 전량 pull 훅 제공 — 현재 범위 out | 폴링 오버헤드 최소화 |
| Q3 (버전 보고) | `device_id` 끝에 `@v1` suffix 추가 검토, 현재는 `esp8266-01` 그대로 유지 | 다중 버전 관리 미뤄두기 |
| Q4 (버튼 의미) | **토글**로 확정 (기존 하드웨어 UX 보존). "ON 요청"은 프론트/AI 경로가 담당 | 기존 UX 유지 |
