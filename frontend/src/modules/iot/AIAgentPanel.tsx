import { useState } from 'react';
import {
  MdSmartToy,
  MdAir,
  MdWaterDrop,
  MdLightMode,
  MdShield,
  MdSettings,
  MdHistory,
  MdAutoAwesome,
} from 'react-icons/md';
import type { AIAgentStatus, AIDecision } from '@/types';
import CropProfileModal from './CropProfileModal';
import { useAIAgent } from '@/hooks/useAIAgent';

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    emergency: 'bg-red-100 text-red-700',
    high: 'bg-orange-100 text-orange-700',
    medium: 'bg-blue-100 text-blue-700',
    low: 'bg-gray-100 text-gray-600',
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors[priority] || colors.low}`}>
      {priority}
    </span>
  );
}

function SourceBadge({ source }: { source: string }) {
  const colors: Record<string, string> = {
    rule: 'bg-yellow-100 text-yellow-700',
    llm: 'bg-purple-100 text-purple-700',
    tool: 'bg-indigo-100 text-indigo-700',
    manual: 'bg-green-100 text-green-700',
  };
  const labels: Record<string, string> = {
    rule: '규칙',
    llm: 'AI',
    tool: 'AI Tool',
    manual: '수동',
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors[source] || 'bg-gray-100 text-gray-600'}`}>
      {labels[source] || source}
    </span>
  );
}

function ControlCard({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border p-4 space-y-2">
      <div className="flex items-center gap-2">
        {icon}
        <span className="font-semibold text-gray-800 text-sm">{title}</span>
        <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 border border-amber-200 font-medium">
          가상 제어
        </span>
      </div>
      <div className="text-sm text-gray-600">{children}</div>
    </div>
  );
}

function DecisionItem({ decision }: { decision: AIDecision }) {
  const [showTrace, setShowTrace] = useState(false);
  const time = new Date(decision.timestamp).toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
  });
  const typeLabels: Record<string, string> = {
    ventilation: '환기',
    irrigation: '관수',
    lighting: '조명',
    shading: '차광/보온',
  };

  const hasTrace = decision.tool_calls && decision.tool_calls.length > 0;

  return (
    <div className="py-2.5 border-b border-gray-100 last:border-0">
      <div className="flex items-start gap-3">
        <span className="text-xs text-gray-400 mt-0.5 shrink-0 w-12">{time}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-gray-800">
              {typeLabels[decision.control_type] || decision.control_type}
            </span>
            <PriorityBadge priority={decision.priority} />
            <SourceBadge source={decision.source} />
            {hasTrace && (
              <button
                onClick={() => setShowTrace(!showTrace)}
                className="text-xs text-indigo-500 hover:text-indigo-700 underline"
              >
                {showTrace ? '추적 닫기' : `도구 호출 ${decision.tool_calls!.length}건`}
              </button>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-1 leading-relaxed">{decision.reason}</p>
        </div>
      </div>
      {showTrace && decision.tool_calls && (
        <div className="ml-14 mt-2 space-y-1.5">
          {decision.tool_calls.map((tc, i) => (
            <div key={i} className="text-xs bg-gray-50 rounded p-2 font-mono">
              <span className="text-indigo-600 font-semibold">{tc.tool}</span>
              {Object.keys(tc.arguments).length > 0 && (
                <span className="text-gray-500 ml-1">
                  ({Object.entries(tc.arguments).map(([k, v]) => `${k}: ${v}`).join(', ')})
                </span>
              )}
              {tc.result?.success !== undefined && (
                <span className={`ml-2 ${tc.result.success ? 'text-green-600' : 'text-red-600'}`}>
                  {tc.result.success ? 'OK' : 'FAIL'}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AIAgentPanel() {
  const { status, decisions, loading, toggle, updateCropProfile } = useAIAgent();
  const [profileOpen, setProfileOpen] = useState(false);
  const [showAllDecisions, setShowAllDecisions] = useState(false);

  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-6 bg-gray-200 rounded w-48 mb-4" />
        <div className="h-32 bg-gray-100 rounded" />
      </div>
    );
  }

  if (!status) {
    return (
      <div className="card">
        <div className="flex items-center gap-2 text-gray-400">
          <MdSmartToy className="text-2xl" />
          <h3 className="font-semibold">AI Agent 제어</h3>
          <span className="ml-auto text-xs">IoT 서버 연결 대기중...</span>
        </div>
      </div>
    );
  }

  const { control_state: cs, crop_profile } = status;

  return (
    <>
      <div className="card space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <MdSmartToy className="text-2xl text-purple-600" />
            <h3 className="section-title !mb-0">AI Agent 제어</h3>
            {status.enabled && (
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500" />
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setProfileOpen(true)}
              className="p-2 hover:bg-gray-100 rounded-lg text-gray-500"
              title="작물 프로필 설정"
            >
              <MdSettings className="text-lg" />
            </button>
            <button
              onClick={toggle}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                status.enabled
                  ? 'bg-green-100 text-green-700 hover:bg-green-200'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
            >
              {status.enabled ? 'ON' : 'OFF'}
            </button>
          </div>
        </div>

        {/* Crop Info */}
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <MdAutoAwesome className="text-green-500" />
          <span>
            {crop_profile.name} / {crop_profile.growth_stage} / 적정 {crop_profile.optimal_temp[0]}~{crop_profile.optimal_temp[1]}C
          </span>
        </div>

        {/* 4대 제어 카드 */}
        {status.enabled ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <ControlCard
              icon={<MdAir className="text-xl text-blue-500" />}
              title="환기"
            >
              <div className="flex justify-between">
                <span>창문 개방</span>
                <span className="font-semibold text-gray-800">{cs.ventilation.window_open_pct}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
                <div className="bg-blue-500 h-1.5 rounded-full transition-all" style={{ width: `${cs.ventilation.window_open_pct}%` }} />
              </div>
              <div className="flex justify-between mt-1.5">
                <span>팬 속도</span>
                <span className="font-semibold text-gray-800">{cs.ventilation.fan_speed} RPM</span>
              </div>
            </ControlCard>

            <ControlCard
              icon={<MdWaterDrop className="text-xl text-cyan-500" />}
              title="관수/양액"
            >
              <div className="flex justify-between">
                <span>밸브</span>
                <span className={`font-semibold ${cs.irrigation.valve_open ? 'text-cyan-600' : 'text-gray-400'}`}>
                  {cs.irrigation.valve_open ? '열림' : '닫힘'}
                </span>
              </div>
              <div className="flex justify-between mt-1">
                <span>금일 급수량</span>
                <span className="font-semibold text-gray-800">{cs.irrigation.daily_total_L.toFixed(1)}L</span>
              </div>
              <div className="flex justify-between mt-1">
                <span>N:P:K</span>
                <span className="font-semibold text-gray-800">
                  {cs.irrigation.nutrient.N}:{cs.irrigation.nutrient.P}:{cs.irrigation.nutrient.K}
                </span>
              </div>
            </ControlCard>

            <ControlCard
              icon={<MdLightMode className="text-xl text-amber-500" />}
              title="조명"
            >
              <div className="flex justify-between">
                <span>상태</span>
                <span className={`font-semibold ${cs.lighting.on ? 'text-amber-600' : 'text-gray-400'}`}>
                  {cs.lighting.on ? 'ON' : 'OFF'}
                </span>
              </div>
              <div className="flex justify-between mt-1">
                <span>밝기</span>
                <span className="font-semibold text-gray-800">{cs.lighting.brightness_pct}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
                <div className="bg-amber-400 h-1.5 rounded-full transition-all" style={{ width: `${cs.lighting.brightness_pct}%` }} />
              </div>
            </ControlCard>

            <ControlCard
              icon={<MdShield className="text-xl text-emerald-500" />}
              title="차광/보온"
            >
              <div className="flex justify-between">
                <span>차광막</span>
                <span className="font-semibold text-gray-800">{cs.shading.shade_pct}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
                <div className="bg-emerald-400 h-1.5 rounded-full transition-all" style={{ width: `${cs.shading.shade_pct}%` }} />
              </div>
              <div className="flex justify-between mt-1.5">
                <span>보온커튼</span>
                <span className="font-semibold text-gray-800">{cs.shading.insulation_pct}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
                <div className="bg-orange-400 h-1.5 rounded-full transition-all" style={{ width: `${cs.shading.insulation_pct}%` }} />
              </div>
            </ControlCard>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-400">
            <MdSmartToy className="text-4xl mx-auto mb-2 opacity-30" />
            <p className="text-sm">AI Agent가 비활성 상태입니다</p>
            <p className="text-xs mt-1">ON 버튼을 눌러 활성화하세요</p>
          </div>
        )}

        {/* 최근 판단 이력 */}
        {status.enabled && decisions.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <MdHistory className="text-gray-400" />
                <span className="text-sm font-semibold text-gray-700">최근 판단</span>
                <span className="text-xs text-gray-400">({status.total_decisions}건)</span>
              </div>
              {decisions.length > 5 && (
                <button
                  onClick={() => setShowAllDecisions(!showAllDecisions)}
                  className="text-xs text-blue-500 hover:text-blue-700"
                >
                  {showAllDecisions ? '접기' : `전체 ${decisions.length}건 보기`}
                </button>
              )}
            </div>
            <div className="bg-gray-50 rounded-xl p-3 max-h-80 overflow-y-auto">
              {(showAllDecisions ? decisions : decisions.slice(0, 5)).map(d => (
                <DecisionItem key={d.id} decision={d} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 작물 프로필 모달 */}
      <CropProfileModal
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
        current={crop_profile}
        onSave={updateCropProfile}
      />
    </>
  );
}
