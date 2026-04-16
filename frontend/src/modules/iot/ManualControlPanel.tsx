// Design Ref: §4.1 — ManualControlPanel (수동 제어 UI + 시뮬레이션 모드)
import { useEffect, useState, useCallback } from 'react';
import {
  MdAir,
  MdWaterDrop,
  MdLightMode,
  MdShield,
  MdTune,
  MdBugReport,
  MdCircle,
  MdTouchApp,
  MdLock,
  MdLockOpen,
} from 'react-icons/md';
import { useManualControl } from '@/hooks/useManualControl';
import { onControlEvent } from '@/hooks/useSensorData';
import type { ManualControlState } from '@/types';

function SourceBadge({ source }: { source: string }) {
  const styles: Record<string, string> = {
    manual: 'bg-green-100 text-green-700',
    button: 'bg-blue-100 text-blue-700',
    rule: 'bg-yellow-100 text-yellow-700',
    ai: 'bg-purple-100 text-purple-700',
    tool: 'bg-indigo-100 text-indigo-700',
  };
  const labels: Record<string, string> = {
    manual: '수동',
    button: '버튼',
    rule: '규칙',
    ai: 'AI',
    tool: 'AI Tool',
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${styles[source] || 'bg-gray-100 text-gray-600'}`}>
      {labels[source] || source}
    </span>
  );
}

function LedIndicator({ on }: { on: boolean }) {
  return (
    <MdCircle className={`text-xs ${on ? 'text-green-500' : 'text-gray-300'}`} />
  );
}

const ACCENT_CLASSES: Record<string, string> = {
  'blue-500': 'accent-blue-500',
  'amber-500': 'accent-amber-500',
  'emerald-500': 'accent-emerald-500',
  'orange-500': 'accent-orange-500',
};

/** 슬라이더: 드래그 중은 로컬 state, 놓으면 서버 전송 */
function ControlSlider({
  value,
  onChange,
  color,
  disabled,
}: {
  value: number;
  onChange: (val: number) => void;
  color: string;
  disabled?: boolean;
}) {
  const [localValue, setLocalValue] = useState(value);
  const [dragging, setDragging] = useState(false);

  // 외부 값 변경 시 로컬 동기화 (드래그 중이 아닐 때만)
  useEffect(() => {
    if (!dragging) {
      setLocalValue(value);
    }
  }, [value, dragging]);

  const commit = useCallback(() => {
    setDragging(false);
    onChange(localValue);
  }, [localValue, onChange]);

  return (
    <input
      type="range"
      min={0}
      max={100}
      step={10}
      value={dragging ? localValue : value}
      onChange={(e) => {
        const v = Number(e.target.value);
        setLocalValue(v);
        setDragging(true);
      }}
      onMouseUp={commit}
      onTouchEnd={commit}
      onBlur={commit}
      className={`w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer ${ACCENT_CLASSES[color] || ''}`}
      disabled={disabled}
    />
  );
}

function LockButton({ locked, onToggle }: { locked: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`ml-auto p-1 rounded transition-all ${
        locked
          ? 'text-orange-500 hover:bg-orange-50'
          : 'text-gray-300 hover:bg-gray-50'
      }`}
      title={locked ? '수동 잠금 중 (클릭하여 AI 제어 허용)' : 'AI 제어 허용 중'}
    >
      {locked ? <MdLock className="text-base" /> : <MdLockOpen className="text-base" />}
    </button>
  );
}

function VentilationCard({
  state,
  onSlider,
  onButton,
  onUnlock,
}: {
  state: ManualControlState['ventilation'];
  onSlider: (action: Record<string, unknown>) => void;
  onButton: (action: Record<string, unknown>) => void;
  onUnlock: () => void;
}) {
  return (
    <div className={`bg-white rounded-xl border p-4 space-y-3 ${state.locked ? 'ring-1 ring-orange-300' : ''}`}>
      <div className="flex items-center gap-2">
        <MdAir className="text-xl text-blue-500" />
        <span className="font-semibold text-gray-800 text-sm">환기</span>
        <LedIndicator on={state.led_on} />
        <SourceBadge source={state.source} />
        <LockButton locked={state.locked} onToggle={onUnlock} />
      </div>

      <div>
        <div className="flex justify-between text-sm text-gray-600 mb-1">
          <span>창문 개폐율</span>
          <span className="font-semibold text-gray-800">{state.window_open_pct}%</span>
        </div>
        <ControlSlider
          value={state.window_open_pct}
          onChange={(v) => onSlider({ window_open_pct: v })}
          color="blue-500"
        />
      </div>

      <div className="flex justify-between text-sm text-gray-600">
        <span>팬 속도</span>
        <span className="font-semibold text-gray-800">{state.fan_speed} RPM</span>
      </div>
      <div className="flex gap-1">
        {[0, 500, 1000, 1500, 3000].map((rpm) => (
          <button
            key={rpm}
            onClick={() => onButton({ fan_speed: rpm })}
            className={`flex-1 text-xs py-1 rounded ${
              state.fan_speed === rpm
                ? 'bg-blue-500 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {rpm === 0 ? 'OFF' : rpm}
          </button>
        ))}
      </div>
    </div>
  );
}

function IrrigationCard({
  state,
  onCommand,
  onUnlock,
}: {
  state: ManualControlState['irrigation'];
  onCommand: (action: Record<string, unknown>) => void;
  onUnlock: () => void;
}) {
  return (
    <div className={`bg-white rounded-xl border p-4 space-y-3 ${state.locked ? 'ring-1 ring-orange-300' : ''}`}>
      <div className="flex items-center gap-2">
        <MdWaterDrop className="text-xl text-cyan-500" />
        <span className="font-semibold text-gray-800 text-sm">관수/양액</span>
        <LedIndicator on={state.led_on} />
        <SourceBadge source={state.source} />
        <LockButton locked={state.locked} onToggle={onUnlock} />
      </div>

      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-600">밸브</span>
        <button
          onClick={() => onCommand({ valve_open: !state.valve_open })}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
            state.valve_open
              ? 'bg-cyan-500 text-white'
              : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
          }`}
        >
          {state.valve_open ? '열림' : '닫힘'}
        </button>
      </div>

      <div className="flex justify-between text-sm text-gray-600">
        <span>금일 급수량</span>
        <span className="font-semibold text-gray-800">{state.daily_total_L.toFixed(1)}L</span>
      </div>
    </div>
  );
}

function LightingCard({
  state,
  onCommand,
  onUnlock,
}: {
  state: ManualControlState['lighting'];
  onCommand: (action: Record<string, unknown>) => void;
  onUnlock: () => void;
}) {
  return (
    <div className={`bg-white rounded-xl border p-4 space-y-3 ${state.locked ? 'ring-1 ring-orange-300' : ''}`}>
      <div className="flex items-center gap-2">
        <MdLightMode className="text-xl text-amber-500" />
        <span className="font-semibold text-gray-800 text-sm">조명</span>
        <LedIndicator on={state.led_on} />
        <SourceBadge source={state.source} />
        <LockButton locked={state.locked} onToggle={onUnlock} />
      </div>

      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-600">상태</span>
        <button
          onClick={() => onCommand({ on: !state.on, brightness_pct: !state.on ? 60 : 0 })}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
            state.on
              ? 'bg-amber-500 text-white'
              : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
          }`}
        >
          {state.on ? 'ON' : 'OFF'}
        </button>
      </div>

      <div>
        <div className="flex justify-between text-sm text-gray-600 mb-1">
          <span>밝기</span>
          <span className="font-semibold text-gray-800">{state.brightness_pct}%</span>
        </div>
        <ControlSlider
          value={state.brightness_pct}
          onChange={(v) => onCommand({ brightness_pct: v, on: v > 0 })}
          color="amber-500"
          disabled={!state.on}
        />
      </div>
    </div>
  );
}

function ShadingCard({
  state,
  onCommand,
  onUnlock,
}: {
  state: ManualControlState['shading'];
  onCommand: (action: Record<string, unknown>) => void;
  onUnlock: () => void;
}) {
  return (
    <div className={`bg-white rounded-xl border p-4 space-y-3 ${state.locked ? 'ring-1 ring-orange-300' : ''}`}>
      <div className="flex items-center gap-2">
        <MdShield className="text-xl text-emerald-500" />
        <span className="font-semibold text-gray-800 text-sm">차광/보온</span>
        <LedIndicator on={state.led_on} />
        <SourceBadge source={state.source} />
        <LockButton locked={state.locked} onToggle={onUnlock} />
      </div>

      <div>
        <div className="flex justify-between text-sm text-gray-600 mb-1">
          <span>차광막</span>
          <span className="font-semibold text-gray-800">{state.shade_pct}%</span>
        </div>
        <ControlSlider
          value={state.shade_pct}
          onChange={(v) => onCommand({ shade_pct: v })}
          color="emerald-500"
        />
      </div>

      <div>
        <div className="flex justify-between text-sm text-gray-600 mb-1">
          <span>보온커튼</span>
          <span className="font-semibold text-gray-800">{state.insulation_pct}%</span>
        </div>
        <ControlSlider
          value={state.insulation_pct}
          onChange={(v) => onCommand({ insulation_pct: v })}
          color="orange-500"
        />
      </div>
    </div>
  );
}

export default function ManualControlPanel() {
  const {
    controlState,
    simMode,
    setSimMode,
    loading,
    sendCommand,
    sendCommandImmediate,
    simulateButton,
    unlockControl,
    handleControlEvent,
  } = useManualControl();

  // SSE control 이벤트 구독
  useEffect(() => {
    return onControlEvent(handleControlEvent);
  }, [handleControlEvent]);

  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-6 bg-gray-200 rounded w-48 mb-4" />
        <div className="h-40 bg-gray-100 rounded" />
      </div>
    );
  }

  if (!controlState) {
    return (
      <div className="card">
        <div className="flex items-center gap-2 text-gray-400">
          <MdTune className="text-2xl" />
          <h3 className="font-semibold">수동 제어</h3>
          <span className="ml-auto text-xs">IoT 서버 연결 대기중...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="card space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MdTune className="text-2xl text-blue-600" />
          <h3 className="section-title !mb-0">수동 제어</h3>
        </div>
        <button
          onClick={() => setSimMode(!simMode)}
          className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            simMode
              ? 'bg-orange-100 text-orange-700 hover:bg-orange-200'
              : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
          }`}
          title="ESP8266 버튼을 브라우저에서 시뮬레이션"
        >
          <MdBugReport className="text-sm" />
          시뮬레이션 {simMode ? 'ON' : 'OFF'}
        </button>
      </div>

      {/* 4대 제어 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <VentilationCard
          state={controlState.ventilation}
          onSlider={(action) => sendCommand('ventilation', action)}
          onButton={(action) => sendCommandImmediate('ventilation', action)}
          onUnlock={() => unlockControl('ventilation')}
        />
        <IrrigationCard
          state={controlState.irrigation}
          onCommand={(action) => sendCommandImmediate('irrigation', action)}
          onUnlock={() => unlockControl('irrigation')}
        />
        <LightingCard
          state={controlState.lighting}
          onCommand={(action) => sendCommandImmediate('lighting', action)}
          onUnlock={() => unlockControl('lighting')}
        />
        <ShadingCard
          state={controlState.shading}
          onCommand={(action) => sendCommand('shading', action)}
          onUnlock={() => unlockControl('shading')}
        />
      </div>

      {/* 시뮬레이션 바 */}
      {simMode && (
        <div className="bg-orange-50 border border-orange-200 rounded-xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <MdTouchApp className="text-orange-500" />
            <span className="text-sm font-semibold text-orange-700">ESP8266 버튼 시뮬레이션</span>
            <span className="text-xs text-orange-500">(하드웨어 미연결 시 테스트용)</span>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {(['ventilation', 'irrigation', 'lighting', 'shading'] as const).map((ct) => {
              const labels = { ventilation: '환기', irrigation: '관수', lighting: '조명', shading: '차광' };
              const activeStyles: Record<string, string> = {
                ventilation: 'bg-blue-100 border-blue-400 text-blue-700',
                irrigation: 'bg-cyan-100 border-cyan-400 text-cyan-700',
                lighting: 'bg-amber-100 border-amber-400 text-amber-700',
                shading: 'bg-emerald-100 border-emerald-400 text-emerald-700',
              };
              const isActive = controlState[ct].active;
              return (
                <button
                  key={ct}
                  onClick={() => simulateButton(ct)}
                  className={`py-2.5 rounded-lg text-sm font-medium transition-all border-2 ${
                    isActive
                      ? activeStyles[ct]
                      : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300'
                  }`}
                >
                  <div className="text-center">
                    <LedIndicator on={isActive} />
                    <div className="mt-1">{labels[ct]}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
