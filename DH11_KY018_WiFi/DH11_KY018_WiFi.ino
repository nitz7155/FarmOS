#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
// [S1] ESP8266WebServer 제거됨 — 서버 주도 폴링 모델로 전환 (Design §6.2)

// 센서
#define DHT_PIN   D4
#define DHT_TYPE  DHT11
#define LDR_PIN   A0
#define LDR_MIN   0
#define LDR_MAX   8

// LED (출력)
#define LED_FAN   D1  // 환기 (외부)
#define LED_WATER D0  // 관수 (내장 LED, 로직 반전)
#define LED_LIGHT D2  // 조명 (외부)
#define LED_SHADE D8  // 차광 (외부)

// 버튼 (입력)
#define BTN_FAN   D7  // → D1 환기
#define BTN_LIGHT D6  // → D2 조명
#define BTN_SHADE D3  // → D8 차광

DHT dht(DHT_PIN, DHT_TYPE);
WiFiClient wificlient;
// [S1] 로컬 HTTP 서버 인스턴스 제거 — 외부는 서버 /api/v1/control/* 경유로만 제어

const char* ssid = "AndroidHotspot2893";
const char* password = "12123434";

const char* Host = "http://iot.lilpa.moe";
const char* apiPath = "/api/v1/sensors";
const char* apiKey  = "farmos-iot-default-key";
const char* deviceId = "esp8266-01";

// [S2] Control polling — Design Ref: §4.1, §6.3
#define POLL_INTERVAL_MS 2000UL

// [S4] 폴링 타이머 전역화 — handleWifi()가 복구 시 0으로 리셋해 즉시 1회 폴 유도
unsigned long lastPollMs = 0;

// [S4.2] Connectivity Watchdog — 서버 도달 성공 시각 (tickPoll의 HTTP 200 지점에서 갱신)
// TIMEOUT 기준: 테스트 10~15s / 운영 권장 30s / 보수 60s
unsigned long lastServerOkMs = 0;
#define SERVER_DEAD_TIMEOUT_MS 30000UL   // 30초 동안 서버 응답 없으면 ESP 재부팅

// 액추에이터 상태
bool fanOn = false;
bool waterOn = false;
bool lightOn = false;
bool shadeOn = false;

// 인터럽트용 플래그
volatile bool fanPressed = false;
volatile bool lightPressed = false;
volatile bool shadePressed = false;

// 인터럽트 핸들러 — [S1] IRAM_ATTR 마이그레이션 (ESP8266 core 3.x)
IRAM_ATTR void onFanBtn()   { fanPressed = true; }
IRAM_ATTR void onLightBtn() { lightPressed = true; }
IRAM_ATTR void onShadeBtn() { shadePressed = true; }

void setup() {
  Serial.begin(9600);
  dht.begin();

  // LED 핀 출력 + 강제 초기화
  pinMode(LED_FAN, OUTPUT);
  pinMode(LED_WATER, OUTPUT);
  pinMode(LED_LIGHT, OUTPUT);
  pinMode(LED_SHADE, OUTPUT);

  digitalWrite(LED_FAN, LOW);
  digitalWrite(LED_WATER, HIGH);  // 내장 LED 반전 (HIGH = 꺼짐)
  digitalWrite(LED_LIGHT, LOW);
  digitalWrite(LED_SHADE, LOW);

  // 버튼 핀 입력 (내부 풀업)
  pinMode(BTN_FAN, INPUT_PULLUP);
  pinMode(BTN_LIGHT, INPUT_PULLUP);
  pinMode(BTN_SHADE, INPUT_PULLUP);

  // 인터럽트 등록 (FALLING = HIGH→LOW 변화 감지)
  attachInterrupt(digitalPinToInterrupt(BTN_FAN), onFanBtn, FALLING);
  attachInterrupt(digitalPinToInterrupt(BTN_LIGHT), onLightBtn, FALLING);
  attachInterrupt(digitalPinToInterrupt(BTN_SHADE), onShadeBtn, FALLING);

  Serial.print("WIFI Connection Check...");
  // [S4.1] 확실한 STA 모드 + 자동 재접속 (Plan FR-09 보강)
  WiFi.persistent(false);              // flash wear 방지
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WIFI Connected!");
  Serial.print("IP : ");
  Serial.println(WiFi.localIP());
  Serial.print("DNS: ");
  Serial.println(WiFi.dnsIP());
  Serial.print("Domain: ");
  Serial.println(Host);

  // [S1] 로컬 HTTP 서버 시작 코드 제거
  // 프론트엔드 제어는 서버(/api/v1/control) → ESP 폴링 경로로 일원화
  lastServerOkMs = millis();           // [S4.2] watchdog 타이머 시작
  Serial.println("[BOOT] polling mode ready");
}

void loop() {
  // [S1] server.handleClient() 제거
  // [S4] WiFi 끊김/복구 모니터링 — Design Ref: §6.8
  handleWifi();
  checkButtons();
  mirrorLeds();

  // [S2] 폴링 틱 — Design Ref: §6.3
  // Plan SC-1: 프론트 토글 → 5초 내 LED 반응 (폴링 2s + HTTP RTT)
  unsigned long now = millis();
  if (now - lastPollMs >= POLL_INTERVAL_MS) {
    lastPollMs = now;
    tickPoll();
  }

  // 3초마다 센서 읽기 + 서버 전송
  static unsigned long lastSend = 0;
  if (millis() - lastSend < 3000) return;
  lastSend = millis();

  sendToServer();
}

void checkButtons() {
  // [S3] 버튼 눌림 감지 → 서버 /control/report (Plan SC-2, Plan FR-05/06)
  // [S5] 논블로킹 디바운스 — millis() 기반, delay() 제거 (FR-11)
  // 한 틱에 최대 1개 버튼만 처리 → 동시 입력은 다음 loop로 이월
  static unsigned long lastBtnMs = 0;
  if (millis() - lastBtnMs < 200) return;

  if (fanPressed) {
    fanPressed = false;
    fanOn = !fanOn;
    mirrorLeds();
    reportButton("ventilation", fanOn);
    lastBtnMs = millis();
    return;
  }
  if (lightPressed) {
    lightPressed = false;
    lightOn = !lightOn;
    mirrorLeds();
    reportButton("lighting", lightOn);
    lastBtnMs = millis();
    return;
  }
  if (shadePressed) {
    shadePressed = false;
    shadeOn = !shadeOn;
    mirrorLeds();
    reportButton("shading", shadeOn);
    lastBtnMs = millis();
  }
}

void mirrorLeds() {
  // [S4] updateLEDs → mirrorLeds 리네임 — Design Ref: §6.7
  // 서버 SSoT 상태를 LED에 그대로 미러링하는 의미를 이름에 반영
  digitalWrite(LED_FAN, fanOn ? HIGH : LOW);
  digitalWrite(LED_WATER, waterOn ? LOW : HIGH);  // D0 내장 LED 반전
  digitalWrite(LED_LIGHT, lightOn ? HIGH : LOW);
  digitalWrite(LED_SHADE, shadeOn ? HIGH : LOW);
}

// 서버 전송 (3초 주기 + 버튼 즉시 전송 공용)
void sendToServer() {
  float temp = dht.readTemperature();
  float humidity = dht.readHumidity();
  int ldrRaw = analogRead(LDR_PIN);

  float lightPercent = constrain(
    (float)(ldrRaw - LDR_MIN) / (LDR_MAX - LDR_MIN) * 100.0, 0, 100
  );

  if (isnan(temp) || isnan(humidity)) {
    Serial.println("DHT11 Not Found!!!");
    return;
  }

  // [S5] 로그 포맷 통일 — [SENS] 접두사 사용, 장황한 POST/Body/Response 덤프 제거
  Serial.printf("[SENS] t=%.1f h=%.1f%% l=%d->%.0f%% (led fan=%d water=%d light=%d shade=%d)\n",
                temp, humidity, ldrRaw, lightPercent, fanOn, waterOn, lightOn, shadeOn);

  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.setTimeout(5000);
  String url = String(Host) + String(apiPath);
  http.begin(wificlient, url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", apiKey);
  http.addHeader("Bypass-Tunnel-Reminder", "true");

  // [S4] actuators 필드 제거 — 관심사 분리 (Plan FR-07, SC-5)
  // 제어 상태는 /api/v1/control/* 경로로만 동기화하며, 센서 POST는 순수 센서만 전달.
  String json = "{\"device_id\":\"" + String(deviceId) + "\","
                "\"sensors\":{"
                  "\"temperature\":" + String(temp) +
                  ",\"humidity\":" + String(humidity) +
                  ",\"light_intensity\":" + String((int)lightPercent) +
                "}}";

  int httpCode = http.POST(json);
  if (httpCode == 200 || httpCode == 201) {
    Serial.printf("[SENS] POST %d\n", httpCode);
  } else if (httpCode > 0) {
    Serial.printf("[SENS] POST %d body=%s\n", httpCode, http.getString().c_str());
  } else {
    Serial.printf("[SENS] POST err %d (%s)\n", httpCode, http.errorToString(httpCode).c_str());
  }

  http.end();
}

// [S1] handleControl() 제거됨 — 외부 제어는 /api/v1/control/commands 폴링으로 일원화

// ───────────────────────────────────────────────────────────
// [S2] Polling module — Design Ref: §6.4, §6.5, §6.7
// 서버 주도 HTTP 폴링으로 제어 명령을 수신·적용·ack.
// [S4 반영 완료] mirrorLeds() 사용 — 서버 상태를 LED에 미러링.
// ───────────────────────────────────────────────────────────

void applyCommand(const char* ct, JsonObject a) {
  // Design Ref: §6.5 — control_type별 서버 state → 로컬 플래그 매핑
  if (strcmp(ct, "ventilation") == 0) {
    int fs  = a["fan_speed"]       | -1;
    int wop = a["window_open_pct"] | -1;
    if (fs >= 0 || wop >= 0) {
      fanOn = ((fs > 0) || (wop > 0));
    } else if (a.containsKey("active")) {
      fanOn = a["active"].as<bool>();
    }
  } else if (strcmp(ct, "lighting") == 0) {
    if (a.containsKey("on")) {
      lightOn = a["on"].as<bool>();
    } else if (a.containsKey("brightness_pct")) {
      lightOn = (a["brightness_pct"].as<int>() > 0);
    }
  } else if (strcmp(ct, "shading") == 0) {
    if (a.containsKey("shade_pct")) {
      shadeOn = (a["shade_pct"].as<int>() > 0);
    } else if (a.containsKey("active")) {
      shadeOn = a["active"].as<bool>();
    }
  } else if (strcmp(ct, "irrigation") == 0) {
    // Plan FR-08: 관수 LED는 서버 상태 미러링 (버튼 없음)
    if (a.containsKey("valve_open")) {
      waterOn = a["valve_open"].as<bool>();
    } else if (a.containsKey("active")) {
      waterOn = a["active"].as<bool>();
    }
  }
  // 그 외 control_type은 무시 (Plan FR-02)
}

void ackCommands(const String& csv) {
  // Design Ref: §6.7 — CSV control_types → JSON array
  if (csv.length() == 0) return;
  if (WiFi.status() != WL_CONNECTED) return;

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

  String body = String("{\"device_id\":\"") + deviceId +
                "\",\"acknowledged_types\":" + arr + "}";

  HTTPClient http;
  http.setTimeout(5000);
  String url = String(Host) + "/api/v1/control/ack";
  http.begin(wificlient, url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", apiKey);
  http.addHeader("Bypass-Tunnel-Reminder", "true");

  int code = http.POST(body);
  Serial.printf("[ACK]  %s -> HTTP %d\n", csv.c_str(), code);
  http.end();
}

void tickPoll() {
  // Design Ref: §6.4 — GET /control/commands → applyCommand → ackCommands
  // Plan FR-01: 2초 주기 폴링 / FR-10: X-API-Key 헤더 필수
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[POLL] skip: wifi down");
    return;
  }

  HTTPClient http;
  http.setTimeout(5000);
  String url = String(Host) + "/api/v1/control/commands?device_id=" + String(deviceId);
  http.begin(wificlient, url);
  http.addHeader("X-API-Key", apiKey);
  http.addHeader("Bypass-Tunnel-Reminder", "true");

  int code = http.GET();
  if (code != 200) {
    Serial.printf("[POLL] HTTP %d\n", code);
    http.end();
    return;
  }

  // [S4.2] 서버 도달 성공 — Watchdog 타이머 갱신
  lastServerOkMs = millis();

  String body = http.getString();
  http.end();

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    Serial.printf("[POLL] JSON err %s\n", err.c_str());
    return;
  }

  JsonObject cmds = doc["commands"].as<JsonObject>();
  if (cmds.isNull() || cmds.size() == 0) {
    Serial.println("[POLL] 200 empty");               // 하트비트
    return;
  }

  String acks;
  for (JsonPair kv : cmds) {
    const char* ct = kv.key().c_str();
    JsonObject a = kv.value().as<JsonObject>();
    applyCommand(ct, a);
    if (acks.length()) acks += ",";
    acks += ct;
  }

  mirrorLeds();                                     // [S4] 리네임 완료
  Serial.printf("[POLL] 200 ok: applied=%s\n", acks.c_str());
  ackCommands(acks);
}

// ───────────────────────────────────────────────────────────
// [S3] Button report module — Design Ref: §6.6
// 물리 버튼 눌림 → 서버 /control/report (source="button")
// 서버는 update_control_state(source="button")으로 locked=true 자동 설정 →
// AI/프론트가 덮어쓰지 못하도록 보호 (Plan 위험 포인트 해소).
// ───────────────────────────────────────────────────────────

void reportButton(const char* ct, bool on) {
  // Plan FR-05: 버튼 이벤트 즉시 POST
  // Plan FR-06: state 페이로드 규약
  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf("[BTN] %s %s (wifi down, skip report)\n", ct, on ? "ON" : "OFF");
    return;
  }

  char state[96];
  if (strcmp(ct, "ventilation") == 0) {
    snprintf(state, sizeof(state),
      "{\"active\":%s,\"fan_speed\":%d,\"window_open_pct\":%d}",
      on ? "true" : "false", on ? 50 : 0, on ? 50 : 0);
  } else if (strcmp(ct, "lighting") == 0) {
    snprintf(state, sizeof(state),
      "{\"on\":%s,\"brightness_pct\":%d}",
      on ? "true" : "false", on ? 100 : 0);
  } else if (strcmp(ct, "shading") == 0) {
    snprintf(state, sizeof(state),
      "{\"shade_pct\":%d,\"insulation_pct\":0}",
      on ? 100 : 0);
  } else {
    return;   // 미지원 control_type 무시
  }

  char body[224];
  snprintf(body, sizeof(body),
    "{\"device_id\":\"%s\",\"control_type\":\"%s\",\"state\":%s,\"source\":\"button\"}",
    deviceId, ct, state);

  HTTPClient http;
  http.setTimeout(5000);
  String url = String(Host) + "/api/v1/control/report";
  http.begin(wificlient, url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", apiKey);
  http.addHeader("Bypass-Tunnel-Reminder", "true");

  int code = http.POST(body);
  Serial.printf("[BTN] %s -> %s (HTTP %d)\n", ct, on ? "ON" : "OFF", code);
  if (code != 200) {
    Serial.println(body);   // 실패 시만 바디 덤프
  }
  http.end();
}

// ───────────────────────────────────────────────────────────
// [S4] WiFi supervisor — Design Ref: §6.8
// 끊김을 감지하면 재접속 시도, 복구 직후에는 lastPollMs=0으로 밀어
// 즉시 1회 폴링을 유도해 서버 상태로 LED를 재수렴시킨다 (Plan FR-09, SC-4).
// ───────────────────────────────────────────────────────────

void handleWifi() {
  // [S4.1] 3단 재시도 — reconnect() x3 → disconnect+begin() x∞
  // [S4.2] Connectivity Watchdog — WiFi 상태 무관, 서버 폴 실패 N초 누적 시 재부팅
  static bool wasConnected = true;
  static unsigned long lastRetryMs = 0;
  static unsigned long lastWdtLogMs = 0;
  static uint8_t retryCount = 0;

  bool now = (WiFi.status() == WL_CONNECTED);

  if (now && !wasConnected) {
    Serial.print("[WIFI] reconnected, IP=");
    Serial.println(WiFi.localIP());
    lastPollMs = 0;                    // 복구 즉시 1회 폴 (SC-4)
    retryCount = 0;
    // 주의: lastServerOkMs는 tickPoll()에서만 갱신. 재접속만으로는 리셋 X.
  } else if (!now && wasConnected) {
    Serial.println("[WIFI] lost");
    lastRetryMs = 0;
    retryCount = 0;
  }

  // 재접속 루프 (WiFi 끊긴 경우)
  if (!now) {
    if (millis() - lastRetryMs >= 2000) {
      lastRetryMs = millis();
      retryCount++;
      if (retryCount <= 3) {
        Serial.printf("[WIFI] retry #%u (reconnect)\n", retryCount);
        WiFi.reconnect();
      } else {
        Serial.printf("[WIFI] retry #%u (full begin)\n", retryCount);
        WiFi.disconnect(true);
        delay(100);
        WiFi.mode(WIFI_STA);
        WiFi.begin(ssid, password);
      }
    }
  }

  // [S4.2] Watchdog — 무조건 실행, WiFi 상태 무관
  if (lastServerOkMs > 0) {
    unsigned long deadMs = millis() - lastServerOkMs;

    // 3초 간격 상태 로그 (watchdog 살아있음을 가시화)
    if (deadMs >= 3000 && millis() - lastWdtLogMs >= 3000) {
      lastWdtLogMs = millis();
      Serial.printf("[WDT] dead=%lus/%lus wifi=%s\n",
                    deadMs / 1000,
                    SERVER_DEAD_TIMEOUT_MS / 1000,
                    now ? "up" : "down");
    }

    if (deadMs > SERVER_DEAD_TIMEOUT_MS) {
      Serial.printf("[WDT] server dead %lums — ESP.restart()\n", deadMs);
      Serial.flush();
      delay(100);
      ESP.restart();
    }
  }

  wasConnected = now;
}