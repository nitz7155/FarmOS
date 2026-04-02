import { useQuery, useMutation } from '@tanstack/react-query';
import apiClient from '@/lib/api';
import type { Order } from '@/types/order';
import type { OrderCreateRequest } from '@/types/order';

export function useOrders() {
  return useQuery({
    queryKey: ['orders'],
    queryFn: async () => {
      const { data } = await apiClient.get<Order[]>('/api/orders');
      return data;
    },
  });
}

export function useOrder(id: number) {
  return useQuery({
    queryKey: ['orders', 'detail', id],
    queryFn: async () => {
      const { data } = await apiClient.get<Order>(`/api/orders/${id}`);
      return data;
    },
    enabled: !!id,
  });
}

export function useCreateOrder() {
  return useMutation({
    mutationFn: async (body: OrderCreateRequest) => {
      const { data } = await apiClient.post<Order>('/api/orders', body);
      return data;
    },
  });
}
