import { beforeEach, describe, expect, it, vi } from "vitest";
import { runOperation, sendMessage } from "./api";

describe("sendMessage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("sends the session and reset flag to the existing query endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: "session-123",
        context_frame: null,
        tier: "fallback",
        answer: "No match",
        result: null,
        query_id: null,
        query_description: null,
        intent: null,
        entities: [],
        latency_ms: 1,
      }),
    } as Response);

    await sendMessage("hello", {
      session_id: "session-123",
      reset_context: true,
    });

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(request.body as string)).toEqual({
      message: "hello",
      session_id: "session-123",
      reset_context: true,
    });
  });

  it("marks chip taps with from_chip so the backend skips the follow-up classifier", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: "session-123",
        context_frame: null,
        tier: "tier2",
        answer: "…",
        result: null,
        query_id: "T05",
        query_description: null,
        intent: null,
        entities: [],
        latency_ms: 1,
      }),
    } as Response);

    await sendMessage("How many hospitals are empanelled in Lucknow?", {
      session_id: "session-123",
      from_chip: true,
    });

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(request.body as string)).toEqual({
      message: "How many hospitals are empanelled in Lucknow?",
      session_id: "session-123",
      from_chip: true,
    });
  });
});

describe("runOperation", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("posts the typed operation to /operation with the session id", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: "session-123",
        context_frame: null,
        tier: "operation",
        answer: "Total total_claimed across 3 rows: 20,000.",
        result: null,
        query_id: "T02",
        latency_ms: 1,
        operation: "sum",
        operation_mode: "client",
      }),
    } as Response);

    const res = await runOperation("session-123", { operation: "sum" }, "rs_abc");

    const [url, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/operation");
    expect(JSON.parse(request.body as string)).toEqual({
      session_id: "session-123",
      result_set_id: "rs_abc",
      operation: "sum",
    });
    expect(res.operation_mode).toBe("client");
  });

  it("surfaces the 409 detail when the table is stale", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "That table is no longer the active result — re-run the question first." }),
    } as Response);

    await expect(
      runOperation("session-123", { operation: "sum" })
    ).rejects.toThrow(/no longer the active result/);
  });
});
