import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api';
import type { Category } from '@/types/category';

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: async () => {
      const { data } = await apiClient.get<Category[]>('/api/categories');
      return data;
    },
  });
}
