/**
 * 날짜 문자열 유틸 — 로컬 타임존 기준.
 *
 * `toISOString().slice(0, 10)` 패턴은 UTC 기준이라
 * 한국(UTC+9) 오전 9시 이전에 "하루 전" 날짜가 반환되는 버그가 있다.
 * 영농일지처럼 "사용자가 인식하는 오늘"이 중요한 도메인에서는 반드시 로컬 기준을 써야 한다.
 */

/** 로컬 타임존 기준 YYYY-MM-DD 문자열. 기본은 현재 시각. */
export function toLocalDateString(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** "YYYY-MM-DD" 문자열을 로컬 자정의 Date 객체로 파싱. `new Date("YYYY-MM-DD")`는 UTC 자정이라 사용 금지. */
export function parseLocalDate(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}
