import { useState, useEffect, useCallback, useRef } from 'react';
import type { SensorReading, IrrigationEvent, SensorAlert } from '@/types';

const API_BASE = 'http://iot.lilpa.moe/api/v1';
const POLL_INTERVAL = 30000; // 30초 간격 폴링
const DISCONNECT_THRESHOLD = 5; // 연속 5회 실패 시 연결 끊김 판정

interface SensorData {
  latest: SensorReading | null;
  history: SensorReading[];
  alerts: SensorAlert[];
  irrigations: IrrigationEvent[];
  connected: boolean;
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

      if (failCount.current >= DISCONNECT_THRESHOLD) {
        setData(prev => ({ ...prev, connected: false }));
      }
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const timer = setInterval(fetchAll, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [fetchAll]);

  return data;
}
