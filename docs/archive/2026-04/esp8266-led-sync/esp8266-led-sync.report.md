# ESP8266 LED Sync — Completion Report

> **Feature**: esp8266-led-sync
> **Cycle**: PDCA v1 · 2026-04-21 단일 세션 완주
> **Final Match Rate**: **94.2%**
> **Status**: ✅ Completed
> **Lead**: clover0309
> **Documents**:
> - Plan: `docs/01-plan/features/esp8266-led-sync.plan.md`
> - Design: `docs/02-design/features/esp8266-led-sync.design.md`
> - Analysis: `docs/03-analysis/esp8266-led-sync.analysis.md`
> - Implementation: `FarmOS/DH11_KY018_WiFi/DH11_KY018_WiFi.ino` (224 → 478 lines, +113%)

---

## Executive Summary

| Perspective | Planned | Delivered | Metric |
|-------------|---------|-----------|--------|
| **Problem** | ESP 로컬 `/control` 웹서버는 터널 뒤 프론트가 도달 불가 + /sensors에 actuators 혼재로 3자 동기화 깨짐 | 로컬 웹서버 완전 제거, 서버 폴링 모델 일원화, actuators 필드 분리 | 신규 5함수 (tickPoll/applyCommand/ackCommands/reportButton/handleWifi) + 삭제 2함수 (웹서버/handleControl) |
| **Solution** | 2s HTTP 폴링 + 버튼→`/control/report` + LED 미러링 | 동일 + Connectivity Watchdog + 3단 WiFi 재시도 | 설계 초과 3건 |
| **Function/UX** | 프론트→LED ≤5s / 버튼→프론트 ≤2s / 네트워크 복구 재수렴 | 실측 ≤3s / ≤1s / 재부팅 포함 ≤40s | SC 5/6 Met |
| **Core Value** | 현장 LED = 서버 SSoT의 시각적 증거, 3소스(버튼/프론트/AI) 일관 관리 | 달성 — source=button 시 `locked=true`로 AI 덮어쓰기 차단 | 수동 잠금 보호 검증 완료 |

---

## 1. Value Delivered

### 1.1 비즈니스 관점

- **Plan 위험 포인트 완전 해소**: "버튼으로 바꿔도 서버가 모름 → AI가 덮어씀" 문제가 수동 잠금(`locked=true`)으로 차단되어, 현장 작업자의 조작 의도가 1인 농업 자동화 파이프라인에서 존중됨.
- **iot-manual-control 완결**: 서버·프론트 완성 상태에서 반쪽 남았던 ESP8266 Step 2를 종결. Major Feature의 나머지 퍼즐 완성.
- **24/7 무인 운용 가능성 확보**: Connectivity Watchdog(30s)로 좀비 상태 자동 복구. 현장 리셋 버튼 눌러야 했던 과거 운영 부담 소거.

### 1.2 기술 관점

| 지표 | Before | After |
|------|:------:|:-----:|
| 코드 라인 | 224 | 478 |
| 외부 도달 경로 | 2개 (ESP 서버 + /sensors 오염) | 1개 (서버 폴링 단일) |
| 포트 80 노출 | ✓ | ✗ (제거) |
| Free heap 여유 (추정) | ~20KB | ~23KB (웹서버 해제) |
| WiFi 복구 로직 | 없음 | 3단 + 무한 재시도 + 좀비 재부팅 |
| 관심사 분리 | 센서+제어 혼재 | 센서/제어/보고 3분리 |

### 1.3 운영 관점

- 현장 LED = 현재 상태 시각 증거 (누가 조작했든 동일 UI)
- 새 펌웨어 바이너리 1개 → 전 디바이스 배포 가능
- Serial 로그 접두사 체계(`[BOOT] [WIFI] [WDT] [POLL] [BTN] [ACK] [SENS]`)로 디버깅 생산성 향상

---

## 2. Success Criteria Final Status

| SC | Criterion | Status | Evidence |
|----|-----------|:------:|----------|
| SC-1 | 프론트 토글 → ≤5s LED 반응 | ✅ Met | 실측 1.5~3s (polling 2s + HTTP RTT) — Do 세션 curl 테스트로 검증 |
| SC-2 | 버튼 → ≤2s 프론트 반영 | ✅ Met | reportButton 즉시 POST → 서버 SSE broadcast — 실측 0.5~1s |
| SC-3 | AI 경로 일관성 | ✅ Met | applyCommand가 source 무관 동일 경로 처리 |
| SC-4 | 네트워크 회복 재수렴 | ✅ Met | handleWifi 3단 + lastPollMs=0 강제 폴 (hotspot off/on 시나리오 실측) |
| SC-5 | /sensors에 actuators 없음 | ✅ Met | sendToServer JSON 페이로드 정리 완료 |
| SC-6 | 24h heap 안정 | ⚠ Partial | 코드상 누수 없음(`http.end()` 4곳 호출), 실측 스트레스 미수행 — **운영 관찰 항목으로 이월** |

**Overall Success Rate**: 5/6 Met, 1/6 Partial = **92%**

---

## 3. Key Decisions & Outcomes

### Decision Record Chain

| Stage | Decision | Rationale | 실제 결과 |
|-------|----------|-----------|----------|
| [Plan] Transport | HTTP 폴링 | 터널/NAT 안전, 기존 서버 계약 재사용 | ✅ 안정 동작, 신규 서버 엔드포인트 0개 추가 |
| [Plan] Scope | 환기/조명/차광 3버튼 양방향 + 관수 LED 미러링 | 기존 하드웨어 제약 수용 | ✅ 4종 LED 전부 제어, 관수 버튼 확장 가능성 유지 |
| [Design] Architecture | Option C (Pragmatic Balance) | 단일 .ino 유지, 함수 경계 분리, ESP 리소스 안전 | ✅ 478줄 단일 파일, 유지보수 양호 |
| [Design] Button semantic | 토글 의미 | 기존 UX 보존 | ✅ reportButton(ct, !state) 로 일관 구현 |
| [Design] Polling 주기 | 2초 | 반응성 vs 네트워크 부하 균형 | ✅ 체감 지연 1.5~3초로 수용 범위 |
| [Do] WiFi 재시도 | Plan 10회 → 구현 3회 reconnect + ∞ begin | Plan 스펙 초과 달성 (더 견고함) | ✅ 핫스팟 리부팅 시나리오 복구 성공 |
| [Do] Watchdog 추가 | Plan/Design 범위 밖, 필요성 발견 시 긴급 도입 | 좀비 상태 발견 → 자동 복구 필수 | ✅ 30초 타임아웃 실측 검증 |

**Decisions Followed**: 7/7 (기획 이탈 없음, 초과 달성만 존재)

---

## 4. Implementation Journey — 세션 요약

| Session | Scope | 주요 변경 | 결과 |
|---------|-------|----------|------|
| S2 module-poll | tickPoll + applyCommand + ackCommands | +130줄, 폴링 루프 가동 | `[POLL] 200 empty` 확인 |
| S3 module-report | 버튼 → /control/report | +52줄, checkButtons 리팩터 | `[BTN] ventilation -> ON (HTTP 200)` |
| S1 module-bootstrap | 웹서버 제거 + IRAM_ATTR | -17줄 | Heap 3~5KB 확보, deprecated 경고 해소 |
| S4 module-glue | handleWifi + mirrorLeds 리네임 + actuators 삭제 | +27줄 | SC-4/SC-5 달성 |
| S4.1 (긴급) | WiFi 3단 재시도 | handleWifi 강화 | 핫스팟 재부팅 복구 |
| S4.2 (긴급) | Connectivity Watchdog | lastServerOkMs + 30s 타임아웃 | 좀비 자동 재부팅 검증 |
| S5 module-polish | 논블로킹 디바운스 + 로그 정리 | checkButtons 재작성, sendToServer 로그 통일 | 7-접두사 로그 체계 완성 |

---

## 5. Gap Resolution Log

| Gap (Analysis §6) | Severity | 해결 여부 | 조치 |
|-------------------|:--------:|:--------:|------|
| G1. SC-6 (24h heap 안정) 미검증 | Important | 📅 Deferred | 운영 관찰 항목으로 등록, 별도 QA 세션 필요 시 실행 |
| G2. Design 함수명 불일치 (handleButtons/sendSensors) | Minor | 📝 문서 업데이트 예정 | Design §5.1 소급 갱신 권고 (코드 OK) |
| G3. httpGet/httpPostJson 래퍼 미추출 | Minor | ⏭ 유보 | 향후 refactor 세션에서 통합 가능 |
| G4. Watchdog 문서 미반영 | Minor | 📝 본 Report에 기록 완료 | Design §6.8에 subsection 추가 권고 |
| G5. 주석 L45 시간 상수 불일치 | Trivial | ✅ 해결됨 | 30초로 수정 |

**Critical 0건, 즉시 조치 필요한 Gap 없음.**

---

## 6. Runtime Artifacts

### Serial 로그 샘플 (정상 동작)

```
WIFI Connection Check.........
IP : 192.168.43.157
[BOOT] polling mode ready
[POLL] 200 empty
[POLL] 200 empty
[SENS] t=24.1 h=62.3% l=4->50% (led fan=0 water=0 light=0 shade=0)
[SENS] POST 201
[POLL] 200 ok: applied=ventilation,lighting,shading,irrigation
[ACK]  ventilation,lighting,shading,irrigation -> HTTP 200
[BTN]  lighting -> OFF (HTTP 200)
[POLL] 200 empty
```

### Serial 로그 샘플 (복구 시나리오)

```
[WIFI] lost
[WIFI] retry #1 (reconnect)
[WIFI] retry #2 (reconnect)
[WIFI] retry #3 (reconnect)
[WIFI] retry #4 (full begin)
[WDT] dead=3s/30s wifi=down
[WIFI] retry #5 (full begin)
[WDT] dead=9s/30s wifi=down
...
[WIFI] reconnected, IP=192.168.43.157
[POLL] 200 empty
```

### 검증된 curl 시나리오

- 전체 켜기 (4 control_type 동시) → LED 4개 동시 점등 ≤ 3s
- 전체 끄기 → 4개 동시 소등
- 물리 버튼 누름 → 서버 `locked=true, source="button"` 반영
- `curl http://<esp-ip>/control` → Connection refused (웹서버 제거 확인)

---

## 7. 학습 포인트 (향후 PDCA 참조)

### 잘한 점

1. **Design 3옵션 비교 → Option C 선택**이 실제로 적정 복잡도였음. Option B였다면 ESP 리소스 부족 가능.
2. **세션 분할(`--scope module-N`)** 으로 각 세션 변경량 50~130줄 유지 → 각 단계 롤백 용이.
3. **Watchdog 긴급 추가**가 Plan 범위를 벗어났지만, 좀비 상태 실발견 후 즉시 도입 → 실전 문제 반영의 좋은 사례.

### 개선 여지

1. **Plan에 "자동 재시작 정책" 명시 부재** → 다음 유사 임베디드 PDCA에서는 Watchdog을 기본 FR로 포함할 것.
2. **L3 E2E 자동화 미비** → 물리 타이머/카메라 기반 측정 파이프라인이 없어 SC-1/SC-2는 수동 실측. QA 단계가 필요할 경우 Serial Monitor 기반 측정 스크립트 고려.
3. **함수 네이밍 규약** — Design과 실제 구현의 이름 불일치는 처음엔 사소해 보이지만 누적되면 추적성 저하. 다음 세션부터는 Design 쓸 때 "기존 이름 유지/교체" 명시할 것.

### Reusable Patterns

| 패턴 | 재사용 맥락 |
|------|-------------|
| HTTP 폴링 + report + ack 3단 계약 | 다른 임베디드 ↔ 서버 연동 |
| Connectivity Watchdog (앱 레이어) | 네트워크 불안정 환경의 모든 IoT 디바이스 |
| 3단 WiFi 재시도 (reconnect x3 → disconnect+begin x∞) | 모든 ESP8266/ESP32 프로젝트 |
| 논블로킹 디바운스 템플릿 (`static lastMs + millis()`) | 인터럽트 기반 입력 모든 곳 |
| Serial 로그 접두사 체계 | 디바이스 단위 관측성 |

---

## 8. Handoff Checklist

- [x] Plan 문서 (`01-plan`)
- [x] Design 문서 (`02-design`)
- [x] Implementation (`DH11_KY018_WiFi.ino` 478줄)
- [x] Analysis 문서 (`03-analysis`)
- [x] Report 문서 (본 문서, `04-report`)
- [ ] 서버 Design §6.8에 Watchdog 소급 문서화 (권고)
- [ ] 24h 스트레스 실측 (SC-6 완결)
- [ ] OTA 배포 파이프라인 (범위 외, 별도 feature)

---

## 9. Follow-up Candidates

차기 PDCA 후보 (현 feature 범위 외):

| 후보 | 가치 | 우선순위 |
|------|------|:--------:|
| 관수용 물리 버튼 추가 | 4종 완전 양방향 | Medium |
| OTA 펌웨어 업데이트 | 현장 방문 없이 배포 | High |
| ESP32 마이그레이션 (TLS 지원) | 보안 등급 상승 (HTTPS) | Low |
| 다중 ESP 디바이스 지원 | `pending_commands`를 device_id별 분리 | Low |
| Metrics dashboard (free heap / rssi 시계열) | 운영 관측성 | Medium |

---

## 10. Closing

esp8266-led-sync는 iot-manual-control 시리즈의 마지막 퍼즐을 닫았다. 서버-프론트-펌웨어 3-way 동기화가 물리 LED로 실증되었고, 운영 중 나타날 수 있는 네트워크/좀비 이슈에 대한 자가 복구까지 내장했다. Match Rate 94.2%, Critical Gap 0, Plan 대비 초과 달성 3건. **Cycle 종료.**

다음 작업은 본 기능의 실전 24h 관찰 또는 `/pdca archive esp8266-led-sync`.
