export interface ChatLog {
  id: number;
  user_id: number | null;
  intent: string;
  question: string;
  answer: string;
  escalated: boolean;
  rating: number | null;
  created_at: string;
}
