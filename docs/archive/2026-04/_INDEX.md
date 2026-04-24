# Archive Index — 2026-04

| Feature | Archived | Match Rate | Documents |
|---------|----------|:----------:|-----------|
| review-analysis-automation | 2026-04-10 | 96% | plan, design, analysis, report |
| farmos_review_analysis | 2026-04-13 | 96% | prd, plan, design, analysis, report |
| agent-action-history | 2026-04-20 | **98.6%** | plan, design, analysis (v0.4), report (v1.2) — Bridge 실가동 검증 완료, SC 5/5 Met, 런타임 버그 6건 수정, Playwright 8/8 PASS |
| esp8266-led-sync | 2026-04-21 | **94.2%** | plan, design, analysis, report — iot-manual-control Step 2 완결, ESP 웹서버 제거 + 폴링 모델 + Connectivity Watchdog, SC 5/6 Met (24h 실측 이월), 7개 세션 (S1~S5 + S4.1 + S4.2) |
| manual-control-onoff | 2026-04-21 | **98%** | plan, design, analysis, report — 환기/차광 ON/OFF 마스터 스위치, Option C(Pragmatic, 훅 ref + 카드 조립), LightingCard 동형 패턴, SC 5/5 Met, Frontend 3파일 +133/-11, ESP8266/Relay Server 변경 0 |
| fix-toggle-shade-heat | 2026-04-24 | **93%** (Static) | plan, design, analysis, report — D3 버튼 공용 제어 HW 계약 기반 3 레이어(FW/BE/FE) 동기화. firmware shade 분기 동시 토글 + shading payload `on` 필드 추가, ai_agent.py 두 지점 broadcast/persist 순서 교정(프로젝트 불변식), useManualControl 에 source='button' lock 해제 + on derive 이중 안전. 3 파일 +39/-11. Runtime L1/L2/L3 검증은 배포 후 이월 (SC 1 Revised / 1 Partial / 3 Pending runtime) |
