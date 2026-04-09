export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  tier?: "tier1" | "tier2" | "fallback";
  result?: Record<string, unknown>[] | null;
  error?: string | null;
  date_range?: { start_date: string; end_date: string };
  date_filter_applied?: boolean;
  originalQuery?: string;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
}
