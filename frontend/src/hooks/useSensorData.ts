import { useState, useEffect, useCallback } from 'react';
import type { SensorReading, IrrigationEvent, SensorAlert } from '@/types';

const API_BASE = 'http://localhost:8000/api/v1';
const POLL_INTERVAL = 3000; // 3초 간격 폴링

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

  const fetchAll = useCallback(async () => {
    try {
      const opts = { credentials: 'include' as RequestCredentials };
      const [latestRes, historyRes, alertsRes, irrigationsRes] = await Promise.all([
        fetch(`${API_BASE}/sensors/latest`, opts),
        fetch(`${API_BASE}/sensors/history?limit=100`, opts),
        fetch(`${API_BASE}/sensors/alerts`, opts),
        fetch(`${API_BASE}/irrigation/events`, opts),
      ]);

      const latest = await latestRes.json();
      const history = await historyRes.json();
      const alerts = await alertsRes.json();
      const irrigations = await irrigationsRes.json();

      setData({
        latest: latest.timestamp ? latest : null,
        history,
        alerts,
        irrigations,
        connected: true,
      });
    } catch {
      setData(prev => ({ ...prev, connected: false }));
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const timer = setInterval(fetchAll, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [fetchAll]);

  return data;
}
