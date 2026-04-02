export function formatPrice(price: number): string {
  return price.toLocaleString('ko-KR') + '원';
}

export function getDiscountedPrice(price: number, discountRate: number): number {
  return Math.floor(price * (1 - discountRate / 100));
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('ko-KR');
}
