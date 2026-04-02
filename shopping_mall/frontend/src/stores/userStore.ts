import { create } from 'zustand';
import type { User } from '@/types/user';

interface UserState {
  user: User;
  isLoggedIn: boolean;
}

export const useUserStore = create<UserState>(() => ({
  user: { id: 1, name: '홍길동', email: 'user@test.com', phone: '010-1234-5678' },
  isLoggedIn: true,
}));
