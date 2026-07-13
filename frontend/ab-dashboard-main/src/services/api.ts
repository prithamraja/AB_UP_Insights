import type { Chip, Clarification, ContextFrame } from "@/types/chat";

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
  session_id?: string;
  reset_context?: boolean;
  start_date?: string;
  end_date?: string;
  // Tapped chip: the text is a catalog question we generated, so the backend
  // routes it straight to matching instead of the follow-up classifier.
  from_chip?: boolean;
}

export interface ChatResponse {
  session_id: string;
  context_frame: ContextFrame | null;
  tier: "tier1" | "tier2" | "fallback" | "operation" | "clarify";
  answer: string;
  result: Record<string, unknown>[] | null;
  query_id: string | null;
  query_description: string | null;
  intent: string | null;
  entities: { slot: string; value: string; confidence: string }[];
  latency_ms: number;
  date_range?: { start_date: string; end_date: string };
  date_filter_applied?: boolean;
  operation?: string | null;
  operation_mode?: "client" | "requery" | "rejected" | null;
  clarification?: Clarification | null;
  suggestions?: Chip[] | null;
}

export interface OperationArgs {
  operation: string;
  column?: string;
  label?: string;
  n?: number;
  direction?: "asc" | "desc";
  filter_column?: string;
  filter_operator?: string;
  filter_value?: string;
  comparator?: string[];
  comparator_slot?: string;
}

export async function sendMessage(
  message: string,
  options?: {
    session_id?: string;
    reset_context?: boolean;
    start_date?: string;
    end_date?: string;
    from_chip?: boolean;
  }
): Promise<ChatResponse> {
  const url = `${API_CONFIG.baseUrl}${API_CONFIG.endpoint}`;

  const body: ChatRequest = { message };
  if (options?.session_id) body.session_id = options.session_id;
  if (options?.reset_context) body.reset_context = true;
  if (options?.start_date) body.start_date = options.start_date;
  if (options?.end_date) body.end_date = options.end_date;
  if (options?.from_chip) body.from_chip = true;

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

export async function resetContext(sessionId: string): Promise<void> {
  const res = await fetch(`${API_CONFIG.baseUrl}/context/reset`, {
    method: "POST",
    headers: API_CONFIG.headers,
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) throw new Error(`Server error: ${res.status}`);
}

export async function popContext(sessionId: string): Promise<ChatResponse> {
  const res = await fetch(`${API_CONFIG.baseUrl}/context/pop`, {
    method: "POST",
    headers: API_CONFIG.headers,
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) {
    if (res.status === 409) {
      const detail = await res.json().catch(() => null);
      throw new Error(detail?.detail ?? "No earlier question to go back to.");
    }
    throw new Error(`Server error: ${res.status}`);
  }
  return res.json();
}

export async function runOperation(
  sessionId: string,
  args: OperationArgs,
  resultSetId?: string
): Promise<ChatResponse> {
  const res = await fetch(`${API_CONFIG.baseUrl}/operation`, {
    method: "POST",
    headers: API_CONFIG.headers,
    body: JSON.stringify({
      session_id: sessionId,
      ...(resultSetId ? { result_set_id: resultSetId } : {}),
      ...args,
    }),
  });

  if (!res.ok) {
    if (res.status === 409) {
      const detail = await res.json().catch(() => null);
      throw new Error(detail?.detail ?? "That table is no longer the active result.");
    }
    throw new Error(`Server error: ${res.status}`);
  }

  return res.json();
}
