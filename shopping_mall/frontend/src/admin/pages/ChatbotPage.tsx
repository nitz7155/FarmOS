import { useState } from 'react';
import { useChatLogs, useEscalatedChatLogs } from '@/admin/hooks/useChatbot';
import { INTENT_LABEL, INTENT_COLOR_BADGE as INTENT_COLOR } from '@/admin/constants/chatbot';
import { formatDate } from '@/lib/utils';
import type { ChatLog } from '@/admin/types/chatlog';

export default function ChatbotPage() {
  const [tab, setTab] = useState<'all' | 'escalated'>('all');
  const [selected, setSelected] = useState<ChatLog | null>(null);

  const { data: allLogs = [], isLoading: loadingAll } = useChatLogs();
  const { data: escalatedLogs = [], isLoading: loadingEsc } = useEscalatedChatLogs();

  const isLoading = tab === 'all' ? loadingAll : loadingEsc;
  const logs = tab === 'all' ? allLogs : escalatedLogs;

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col">
      {/* 상단 탭 */}
      <div className="px-6 pt-5 pb-0 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xl font-bold text-gray-900">챗봇 대화 관리</h2>
          <span className="text-sm text-gray-400">{logs.length}건</span>
        </div>
        <div className="flex gap-0">
          {(['all', 'escalated'] as const).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); setSelected(null); }}
              className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t
                  ? 'border-[#03C75A] text-[#03C75A]'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t === 'all' ? '전체 대화' : (
                <span className="flex items-center gap-1.5">
                  에스컬레이션
                  {escalatedLogs.length > 0 && (
                    <span className="bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5 leading-none">
                      {escalatedLogs.length}
                    </span>
                  )}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* 채널톡 레이아웃 */}
      <div className="flex flex-1 overflow-hidden">
        {/* 대화 목록 */}
        <div className="w-72 shrink-0 border-r border-gray-200 bg-white overflow-y-auto">
          {isLoading ? (
            <div className="p-6 text-center text-gray-400 text-sm">로딩 중...</div>
          ) : logs.length === 0 ? (
            <div className="p-6 text-center text-gray-400 text-sm">대화 내역이 없습니다.</div>
          ) : (
            logs.map((log) => (
              <button
                key={log.id}
                onClick={() => setSelected(log)}
                className={`w-full text-left px-4 py-3.5 border-b border-gray-100 hover:bg-gray-50 transition-colors ${
                  selected?.id === log.id ? 'bg-green-50 border-l-4 border-l-[#03C75A]' : 'border-l-4 border-l-transparent'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium text-gray-700">
                      {log.user_id ? `회원 #${log.user_id}` : '비회원'}
                    </span>
                    {log.escalated && (
                      <span className="w-2 h-2 rounded-full bg-red-500 shrink-0" title="에스컬레이션" />
                    )}
                  </div>
                  <span className="text-xs text-gray-400 shrink-0">{formatDate(log.created_at, 'MM/dd HH:mm')}</span>
                </div>
                <p className="text-xs text-gray-500 truncate mb-1.5">{log.question}</p>
                <span
                  className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${
                    INTENT_COLOR[log.intent] ?? 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {INTENT_LABEL[log.intent] ?? log.intent}
                </span>
              </button>
            ))
          )}
        </div>

        {/* 대화 상세 */}
        <div className="flex-1 bg-gray-50 overflow-y-auto">
          {selected ? (
            <div className="max-w-2xl mx-auto p-6 space-y-4">
              {/* 메타 정보 */}
              <div className="bg-white rounded-xl border border-gray-200 px-5 py-4 flex items-center gap-4 text-sm text-gray-500">
                <span>
                  <span className="font-medium text-gray-700">사용자:</span>{' '}
                  {selected.user_id ? `회원 #${selected.user_id}` : '비회원'}
                </span>
                <span className="text-gray-300">|</span>
                <span>
                  <span className="font-medium text-gray-700">시각:</span>{' '}
                  {formatDate(selected.created_at)}
                </span>
                <span className="text-gray-300">|</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    INTENT_COLOR[selected.intent] ?? 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {INTENT_LABEL[selected.intent] ?? selected.intent}
                </span>
                {selected.escalated && (
                  <span className="ml-auto text-red-500 font-semibold text-xs flex items-center gap-1">
                    ⚠ 상담원 연결 필요
                  </span>
                )}
              </div>

              {/* 대화 버블 */}
              <div className="space-y-4">
                {/* 사용자 질문 */}
                <div className="flex justify-end">
                  <div className="max-w-[75%] bg-[#03C75A] text-white px-4 py-3 rounded-2xl rounded-br-sm text-sm leading-relaxed">
                    {selected.question}
                  </div>
                </div>

                {/* 봇 답변 */}
                <div className="flex justify-start gap-2">
                  <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-base shrink-0">
                    🤖
                  </div>
                  <div className="max-w-[75%] bg-white border border-gray-200 px-4 py-3 rounded-2xl rounded-bl-sm text-sm leading-relaxed text-gray-800 whitespace-pre-wrap">
                    {selected.answer}
                  </div>
                </div>
              </div>

              {/* 평점 */}
              {selected.rating != null && (
                <div className="bg-white rounded-xl border border-gray-200 px-5 py-3 text-sm text-gray-500">
                  고객 평점:{' '}
                  <span className="text-yellow-500 font-medium">{'★'.repeat(selected.rating)}{'☆'.repeat(5 - selected.rating)}</span>
                  {' '}({selected.rating}/5)
                </div>
              )}
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-gray-400">
              <div className="text-center space-y-2">
                <div className="text-4xl">💬</div>
                <p className="text-sm">목록에서 대화를 선택하세요</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
