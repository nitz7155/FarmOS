// Chat related types

export interface ChatSession {
  id: number;
  userId: number;
  status: 'active' | 'closed';
  title: string | null;
  createdAt: string;
  updatedAt: string;
  closedAt: string | null;
  messageCount?: number;
  messagePreview?: string;
}

export interface ChatMessage {
  role: 'user' | 'bot';
  text: string;
  intent?: string;
  escalated?: boolean;
  createdAt?: string;
}

export interface ChatSessionMessage {
  role: 'user' | 'bot';
  text: string;
  intent?: string;
  escalated?: boolean;
  createdAt?: string;
}

export type ChatView = 'list' | 'chat';
