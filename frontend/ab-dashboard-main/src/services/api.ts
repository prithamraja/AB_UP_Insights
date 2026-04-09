const API_CONFIG = {
  baseUrl: import.meta.env.VITE_API_BASE_URL || "https://sariah-petechial-proportionately.ngrok-free.dev",
  endpoint: "/query",
  headers: {
    "Content-Type": "application/json",
  } as Record<string, string>,
};

export function configureApi(config: Partial<typeof API_CONFIG>) {
  Object.assign(API_CONFIG, config);
}

export interface ChatRequest {
  message: string;
  start_date?: string;
  end_date?: string;
}

export interface ChatResponse {
  tier: "tier1" | "tier2" | "fallback";
  answer: string;
  result: Record<string, unknown>[] | null;
  match_id: string | null;
  score: number | null;
  latency_ms: number;
  date_range?: { start_date: string; end_date: string };
  date_filter_applied?: boolean;
}

export async function sendMessage(
  message: string,
  options?: { start_date?: string; end_date?: string }
): Promise<ChatResponse> {
  const url = `${API_CONFIG.baseUrl}${API_CONFIG.endpoint}`;

  const body: ChatRequest = { message };
  if (options?.start_date) body.start_date = options.start_date;
  if (options?.end_date) body.end_date = options.end_date;

  const res = await fetch(url, {
    method: "POST",
    headers: API_CONFIG.headers,
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(`Server error: ${res.status}`);
  }

  return res.json();
}
