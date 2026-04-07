#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <DHT.h>

#define DHT_PIN D4
#define DHT_TYPE DHT11
#define LDR_PIN A0

// 조도 센서 값 조정. 실측 기준으로 진행. 범위는 0~8 (저항없음 이슈로 인해 보정처리.)
#define LDR_MIN 0 // 빛 안볼때 최저치
#define LDR_MAX 8 // 빛 볼때 최대치

DHT dht(DHT_PIN, DHT_TYPE);
WiFiClient wificlient;

const char* ssid = "hi-1-2G";
const char* password = "0234780008";

// ★ localtunnel 주소 (HTTP로 접속 — ESP8266 TLS 한계 우회)
// lt --port 8000 으로 실행 후 나오는 주소를 여기에 붙여넣기
const char* Host = "http://iot.lilpa.moe";

const char* apiPath = "/api/v1/sensors";
const char* apiKey  = "farmos-iot-default-key";
const char* deviceId = "esp8266-01";


void setup() {
  Serial.begin(9600);
  dht.begin();

  Serial.print("WIFI Connection Check...");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WIFI Connected!");
  Serial.print("IP : ");
  Serial.println(WiFi.localIP());

  // DHCP에서 받은 DNS 확인
  Serial.print("DNS: ");
  Serial.println(WiFi.dnsIP());

  Serial.print("Domain: ");
  Serial.println(Host);
}

void loop() {
  float temp = dht.readTemperature();
  float humidity = dht.readHumidity();
  int ldrRaw = analogRead(LDR_PIN);

  float lightPercent = constrain(
    // 여기서 조도값을 보정을 쳐줌.
    (float)(ldrRaw - LDR_MIN) / (LDR_MAX - LDR_MIN) * 100.0, 0, 100
  );

  if(isnan(temp) || isnan(humidity)) {
    Serial.println("DHT11 Not Found!!!");
    delay(2000);
    return;
  }

  Serial.printf("temp : %.1f | humidity: %.1f%% | light raw : %d -> %.0f%%\n", temp, humidity, ldrRaw, lightPercent);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.setTimeout(10000);
    String url = String(Host) + String(apiPath);
    http.begin(wificlient, url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", apiKey);
    http.addHeader("Bypass-Tunnel-Reminder", "true");

    // 백엔드 SensorDataIn 스키마에 맞춘 JSON
    String json = "{\"device_id\":\"" + String(deviceId) + "\","
                  "\"sensors\":{"
                    "\"temperature\":" + String(temp) +
                    ",\"humidity\":" + String(humidity) +
                    ",\"light_intensity\":" + String((int)lightPercent) +
                  "}}";

    Serial.println("POST -> " + url);
    Serial.println("Body: " + json);

    int httpCode = http.POST(json);
    Serial.println("Server Say : " + String(httpCode));

    if (httpCode > 0) {
      Serial.println("Response: " + http.getString());
    } else {
      Serial.println("Connection failed: " + http.errorToString(httpCode));
    }

    http.end();
  }
  delay(30000);
}
