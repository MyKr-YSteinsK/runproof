import { afterEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { InvestigationEvidence } from "./CompetitionAgentPage";
import {
  agentApi, agentMode, investigationSchema, mayStart, type AgentCapability, type AgentInvestigation,
} from "./competitionAgentApi";
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

it("renders unknown fault evidence separately from yes, no, and task completion", () => {
  const report: AgentInvestigation = {
    schema: investigationSchema,
    issuer: "NOT_ESTABLISHED",
    session: {
      session_id: "a".repeat(32), mode: agentMode, profile: "effectwitness-reference/1",
      status: "RUNNING", provider_reservations: 0, candidates: [], source: {}, events: [], rounds: [],
    },
    summary: {
      next: "MANUAL_REVIEW_NO_REPLAY",
      task_completion: "NOT_ESTABLISHED",
      domains: [{
        domain: "order", effect: "COMMITTED", gaps: ["FAULT_EVENT_NOT_PERSISTED"],
        fault: { planned: true, triggered: null, observed: null, agent_exposed: false },
      }],
    },
  };
  const en = renderToStaticMarkup(<InvestigationEvidence report={report} label={(_, value) => value} />);
  expect(en).toContain("<dt>Planned</dt><dd>Yes</dd>");
  expect(en).toContain("<dt>Triggered</dt><dd>Unknown</dd>");
  expect(en).toContain("<dt>Observed</dt><dd>Unknown</dd>");
  expect(en).toContain("<dt>Agent saw the raw fault</dt><dd>No</dd>");
  expect(en).toContain("COMMITTED");
  expect(en).toContain("Task completion unconfirmed");
  expect(en).toContain("Issuer not established");
  expect(en).toContain("Use the CLI to check the exported content.");

  const withMissingFlag = structuredClone(report);
  delete withMissingFlag.summary.domains[0].fault.observed;
  const zh = renderToStaticMarkup(<InvestigationEvidence report={withMissingFlag} label={value => value} />);
  expect(zh).toContain("<dt>已观察</dt><dd>未知</dd>");
  expect(zh).toContain("缺少持久化故障事件");

  const legacy = { ...report, schema: "runproof-agent-investigation/v1" };
  const old = renderToStaticMarkup(<InvestigationEvidence report={legacy} label={(_, value) => value} />);
  expect(old).toContain("Use the original verifier");
  expect(old).not.toContain("<dt>Triggered</dt>");
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
