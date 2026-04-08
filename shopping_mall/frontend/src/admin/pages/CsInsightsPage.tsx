import { useChatLogs, useEscalatedChatLogs } from '@/admin/hooks/useChatbot';
import { INTENT_LABEL_FULL as INTENT_LABEL, INTENT_COLOR_BAR as INTENT_COLOR } from '@/admin/constants/chatbot';
import type { ChatLog } from '@/admin/types/chatlog';

export default function CsInsightsPage() {
  const { data: allLogs = [], isLoading } = useChatLogs();
  const { data: escalatedLogs = [] } = useEscalatedChatLogs();

  if (isLoading) {
    return <div className="p-6 text-gray-400">로딩 중...</div>;
  }

  const total = allLogs.length;
  const escalatedCount = escalatedLogs.length;
  const resolvedCount = total - escalatedCount;
  const resolveRate = total > 0 ? Math.round((resolvedCount / total) * 100) : 0;

  // 의도별 집계
  const intentCounts: Record<string, number> = {};
  for (const log of allLogs) {
    intentCounts[log.intent] = (intentCounts[log.intent] ?? 0) + 1;
  }
  const sortedIntents = Object.entries(intentCounts).sort((a, b) => b[1] - a[1]);

  // 평점 집계 (rating이 있는 로그만)
  const ratedLogs = allLogs.filter((l: ChatLog) => l.rating != null);
  const avgRating =
    ratedLogs.length > 0
      ? (ratedLogs.reduce((sum: number, l: ChatLog) => sum + (l.rating ?? 0), 0) / ratedLogs.length).toFixed(1)
      : null;

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-xl font-bold text-gray-900">CS 인사이트</h2>

      {/* 핵심 지표 카드 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="총 문의" value={`${total}건`} sub="전체 대화 수" color="text-gray-800" />
        <StatCard
          label="자동 해결"
          value={`${resolveRate}%`}
          sub={`${resolvedCount}건 처리 완료`}
          color="text-[#03C75A]"
        />
        <StatCard
          label="에스컬레이션"
          value={`${escalatedCount}건`}
          sub="상담원 연결 필요"
          color={escalatedCount > 0 ? 'text-red-500' : 'text-gray-400'}
        />
        <StatCard
          label="평균 평점"
          value={avgRating ? `${avgRating} / 5` : '-'}
          sub={avgRating ? `${ratedLogs.length}건 평가됨` : '평점 없음'}
          color="text-yellow-500"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 의도별 분포 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
          <h3 className="font-semibold text-gray-700">의도별 문의 분포</h3>
          {sortedIntents.length === 0 ? (
            <p className="text-sm text-gray-400">데이터 없음</p>
          ) : (
            <div className="space-y-3">
              {sortedIntents.map(([intent, count]) => {
                const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                return (
                  <div key={intent}>
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className="text-gray-600">{INTENT_LABEL[intent] ?? intent}</span>
                      <span className="font-medium text-gray-700">{count}건 ({pct}%)</span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${INTENT_COLOR[intent] ?? 'bg-gray-400'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 에스컬레이션 목록 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
          <h3 className="font-semibold text-gray-700">
            최근 에스컬레이션
            {escalatedCount > 0 && (
              <span className="ml-2 text-xs bg-red-100 text-red-600 px-2 py-0.5 rounded-full">
                {escalatedCount}건
              </span>
            )}
          </h3>
          {escalatedLogs.length === 0 ? (
            <p className="text-sm text-gray-400">에스컬레이션 없음 ✅</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {escalatedLogs.slice(0, 10).map((log: ChatLog) => (
                <div key={log.id} className="border border-red-100 bg-red-50 rounded-lg px-3 py-2.5">
                  <p className="text-sm text-gray-700 truncate">{log.question}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {log.user_id ? `회원 #${log.user_id}` : '비회원'} · {new Date(log.created_at).toLocaleDateString('ko-KR')}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub: string;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      <p className="text-xs text-gray-400 mt-1">{sub}</p>
    </div>
  );
}
