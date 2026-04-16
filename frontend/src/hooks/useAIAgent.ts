import { useState, useEffect, useCallback } from 'react';
import type { AIAgentStatus, AIDecision, CropProfile } from '@/types';
import { onAIDecisionEvent } from '@/hooks/useSensorData';

const API_BASE = 'https://iot.lilpa.moe/api/v1';
const POLL_INTERVAL = 60000; // SSE가 실시간 처리하므로 폴링은 60초 fallback

export function useAIAgent() {
  const [status, setStatus] = useState<AIAgentStatus | null>(null);
  const [decisions, setDecisions] = useState<AIDecision[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const [statusRes, decisionsRes] = await Promise.all([
        fetch(`${API_BASE}/ai-agent/status`, { credentials: 'omit' }),
        fetch(`${API_BASE}/ai-agent/decisions?limit=20`, { credentials: 'omit' }),
      ]);
      if (statusRes.ok) {
        const data = await statusRes.json();
        setStatus(data);
      }
      if (decisionsRes.ok) {
        const data = await decisionsRes.json();
        setDecisions(data);
      }
    } catch {
      // 무시
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const timer = setInterval(fetchStatus, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [fetchStatus]);

  // SSE ai_decision 이벤트 → 판단 즉시 반영
  useEffect(() => {
    return onAIDecisionEvent((data) => {
      const decision = data as AIDecision;

      // decisions 목록 맨 앞에 추가
      setDecisions(prev => [decision, ...prev].slice(0, 20));

      // status의 latest_decision + total_decisions 업데이트
      setStatus(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          latest_decision: decision,
          total_decisions: prev.total_decisions + 1,
        };
      });

      // control_state도 AI 판단 결과로 업데이트
      if (decision.control_type && decision.action) {
        setStatus(prev => {
          if (!prev) return prev;
          const ct = decision.control_type as keyof typeof prev.control_state;
          if (!(ct in prev.control_state)) return prev;
          return {
            ...prev,
            control_state: {
              ...prev.control_state,
              [ct]: { ...prev.control_state[ct], ...decision.action },
            },
          };
        });
      }
    });
  }, []);

  const toggle = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/ai-agent/toggle`, {
        method: 'POST',
        credentials: 'omit',
      });
      if (res.ok) {
        await fetchStatus();
      }
    } catch {
      // 무시
    }
  }, [fetchStatus]);

  const updateCropProfile = useCallback(async (profile: CropProfile) => {
    try {
      const res = await fetch(`${API_BASE}/ai-agent/crop-profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'omit',
        body: JSON.stringify(profile),
      });
      if (res.ok) {
        await fetchStatus();
      }
    } catch {
      // 무시
    }
  }, [fetchStatus]);

  const override = useCallback(async (controlType: string, values: Record<string, unknown>, reason: string) => {
    try {
      await fetch(`${API_BASE}/ai-agent/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'omit',
        body: JSON.stringify({ control_type: controlType, values, reason }),
      });
      await fetchStatus();
    } catch {
      // 무시
    }
  }, [fetchStatus]);

  return { status, decisions, loading, toggle, updateCropProfile, override, refetch: fetchStatus };
}
