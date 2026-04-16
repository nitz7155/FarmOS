import { useState, useEffect, useCallback, useRef } from 'react';
import type { SensorReading, IrrigationEvent, SensorAlert, ControlEvent } from '@/types';

const API_BASE = 'https://iot.lilpa.moe/api/v1';
const FULL_SYNC_INTERVAL = 60000; // 전체 동기화는 60초마다 (fallback)

interface SensorData {
  latest: SensorReading | null;
  history: SensorReading[];
  alerts: SensorAlert[];
  irrigations: IrrigationEvent[];
  connected: boolean;
}

// Design Ref: §4.4 — SSE control 이벤트 콜백 지원
type ControlEventHandler = (event: ControlEvent) => void;
const _controlHandlers: Set<ControlEventHandler> = new Set();

export function onControlEvent(handler: ControlEventHandler) {
  _controlHandlers.add(handler);
  return () => { _controlHandlers.delete(handler); };
}

// SSE ai_decision 이벤트 콜백
type AnyEventHandler = (data: unknown) => void;
const _aiDecisionHandlers: Set<AnyEventHandler> = new Set();

export function onAIDecisionEvent(handler: AnyEventHandler) {
  _aiDecisionHandlers.add(handler);
  return () => { _aiDecisionHandlers.delete(handler); };
}

export function useSensorData() {
  const [data, setData] = useState<SensorData>({
    latest: null,
    history: [],
    alerts: [],
    irrigations: [],
    connected: false,
  });

  const failCount = useRef(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  // 전체 데이터 동기화 (초기 로드 + 주기적 fallback)
  const fetchAll = useCallback(async () => {
    try {
      const [latestRes, historyRes, alertsRes, irrigationsRes] = await Promise.all([
        fetch(`${API_BASE}/sensors/latest`),
        fetch(`${API_BASE}/sensors/history?limit=100`),
        fetch(`${API_BASE}/sensors/alerts`),
        fetch(`${API_BASE}/irrigation/events`),
      ]);

      const latest = await latestRes.json();
      const history = await historyRes.json();
      const alerts = await alertsRes.json();
      const irrigations = await irrigationsRes.json();

      failCount.current = 0;

      setData({
        latest: latest.timestamp ? latest : null,
        history,
        alerts,
        irrigations,
        connected: true,
      });
    } catch {
      failCount.current += 1;
      if (failCount.current >= 5) {
        setData(prev => ({ ...prev, connected: false }));
      }
    }
  }, []);

  // SSE 연결
  useEffect(() => {
    // 초기 전체 로드
    fetchAll();

    const es = new EventSource(`${API_BASE}/sensors/stream`);
    eventSourceRef.current = es;

    es.addEventListener('sensor', (e) => {
      try {
        const reading = JSON.parse(e.data) as SensorReading;
        setData(prev => ({
          ...prev,
          latest: reading,
          history: [...prev.history.slice(-(99)), reading],
          connected: true,
        }));
      } catch (err) {
        console.warn('[SSE] sensor parse error:', err);
      }
    });

    es.addEventListener('alert', (e) => {
      try {
        const alert = JSON.parse(e.data) as SensorAlert;
        setData(prev => ({
          ...prev,
          alerts: [alert, ...prev.alerts],
        }));
      } catch (err) {
        console.warn('[SSE] alert parse error:', err);
      }
    });

    es.addEventListener('irrigation', (e) => {
      try {
        const event = JSON.parse(e.data) as IrrigationEvent;
        setData(prev => ({
          ...prev,
          irrigations: [event, ...prev.irrigations],
        }));
      } catch (err) {
        console.warn('[SSE] irrigation parse error:', err);
      }
    });

    es.addEventListener('control', (e) => {
      try {
        const controlEvent = JSON.parse(e.data) as ControlEvent;
        _controlHandlers.forEach(handler => handler(controlEvent));
      } catch (err) {
        console.warn('[SSE] control parse error:', err);
      }
    });

    es.addEventListener('ai_decision', (e) => {
      try {
        const decision = JSON.parse(e.data);
        _aiDecisionHandlers.forEach(handler => handler(decision));
      } catch (err) {
        console.warn('[SSE] ai_decision parse error:', err);
      }
    });

    es.onopen = () => {
      failCount.current = 0;
      setData(prev => ({ ...prev, connected: true }));
    };

    es.onerror = () => {
      // SSE 끊기면 connected 상태 업데이트
      // EventSource는 자동 재연결하므로 즉시 false로 바꾸지 않음
      failCount.current += 1;
      if (failCount.current >= 5) {
        setData(prev => ({ ...prev, connected: false }));
      }
    };

    // 전체 동기화 fallback (history 정합성 보장)
    const syncTimer = setInterval(fetchAll, FULL_SYNC_INTERVAL);

    return () => {
      es.close();
      eventSourceRef.current = null;
      clearInterval(syncTimer);
    };
  }, [fetchAll]);

  return data;
}
