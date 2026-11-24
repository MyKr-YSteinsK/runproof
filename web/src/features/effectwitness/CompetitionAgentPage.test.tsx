import { afterEach, describe, expect, it, vi } from "vitest";
import { agentApi, agentMode, mayStart, type AgentCapability } from "./competitionAgentApi";
import { mode, productApi } from "./productLocalApi";

afterEach(() => vi.unstubAllGlobals());

describe("reference Agent admission", () => {
  const fresh: AgentCapability = {
    instance: "1".repeat(32), owner: "test", readonly: false, version: "v2", mode: agentMode, remaining: 1, blocked: false, provider_reservations: 0,
    latest: null, profile: "effectwitness-reference/1", tools: ["refund_order", "apply_config"],
  };
  it("allows only an empty offline Agent owner", () => {
    expect(mayStart(fresh, false)).toBe(true);
    expect(mayStart(null, false)).toBe(false);
    expect(mayStart(fresh, true)).toBe(false);
    expect(mayStart({ ...fresh, mode: "CONTROLLED_LOCAL_PRODUCT" }, false)).toBe(false);
    expect(mayStart({ ...fresh, remaining: 0 }, false)).toBe(false);
    expect(mayStart({ ...fresh, latest: "already-started" }, false)).toBe(false);
    expect(mayStart({ ...fresh, blocked: true }, false)).toBe(false);
    expect(mayStart({ ...fresh, provider_reservations: 1 }, false)).toBe(false);
  });
});

it("sends one request per session start and preserves each local profile's mode", async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response('{"session_id":"agent"}'))
    .mockResolvedValueOnce(new Response('{"session_id":"rule-policy"}'))
    .mockResolvedValueOnce(new Response(null, { status: 503 }));
  vi.stubGlobal("fetch", fetch);

  await expect(agentApi.start("agent-request")).resolves.toMatchObject({ session_id: "agent" });
  await expect(productApi.create("rule-request")).resolves.toMatchObject({ session_id: "rule-policy" });
  await expect(agentApi.request("agent/request")).rejects.toThrow("GATEWAY_503");

  expect(fetch.mock.calls).toEqual([
    ["/effectwitness-product-api/session", expect.objectContaining({
      method: "POST", cache: "no-store", signal: expect.any(AbortSignal),
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: agentMode, request_id: "agent-request" }),
    })],
    ["/effectwitness-product-api/session", expect.objectContaining({
      method: "POST", cache: "no-store", signal: expect.any(AbortSignal),
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, request_id: "rule-request" }),
    })],
    ["/effectwitness-product-api/request/agent%2Frequest", expect.objectContaining({
      cache: "no-store", signal: expect.any(AbortSignal),
    })],
  ]);
});
