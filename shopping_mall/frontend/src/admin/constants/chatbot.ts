export const INTENT_LABEL: Record<string, string> = {
  delivery: '배송',
  stock: '재고',
  storage: '보관',
  exchange: '교환/환불',
  season: '제철',
  other: '기타',
};

export const INTENT_LABEL_FULL: Record<string, string> = {
  delivery: '📦 배송',
  stock: '🍎 재고',
  storage: '❄️ 보관',
  exchange: '↩️ 교환/환불',
  season: '🌸 제철',
  other: '💬 기타',
};

export const INTENT_COLOR_BADGE: Record<string, string> = {
  delivery: 'bg-blue-100 text-blue-700',
  stock: 'bg-purple-100 text-purple-700',
  storage: 'bg-cyan-100 text-cyan-700',
  exchange: 'bg-orange-100 text-orange-700',
  season: 'bg-green-100 text-green-700',
  other: 'bg-gray-100 text-gray-600',
};

export const INTENT_COLOR_BAR: Record<string, string> = {
  delivery: 'bg-blue-500',
  stock: 'bg-purple-500',
  storage: 'bg-cyan-500',
  exchange: 'bg-orange-500',
  season: 'bg-green-500',
  other: 'bg-gray-400',
};
