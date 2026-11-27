import { createHash } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { InvestigationEvidence, publishInvestigation } from "./CompetitionAgentPage";
import {
  agentApi, agentExportKind, agentMode, investigationSchema, mayStart, readAgentInvestigation, readAgentSession,
  readAgentWitness, type AgentCapability, type AgentInvestigation, type AgentSession,
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

describe("independent Reference Agent reads", () => {
  const owner = "1".repeat(32);
  const request = "11111111-1111-4111-8111-111111111111";
  const session: AgentSession = {
    owner_id: owner, request_id: request, session_id: "a".repeat(32), mode: agentMode,
    profile: "effectwitness-reference/1", status: "COMPLETED", provider_reservations: 0,
    candidates: [], events: [], rounds: [], source: {},
  };
  const capability: AgentCapability = {
    instance: owner, owner: "test", readonly: true, version: "v2", mode: agentMode,
    remaining: 0, blocked: false, provider_reservations: 0, latest: session.session_id,
    profile: session.profile, tools: [],
  };
  const witness = { schema: "runproof-competition-agent-witness/v2", session };
  const investigation = (record: AgentSession): AgentInvestigation => ({
    schema: investigationSchema, issuer: "NOT_ESTABLISHED", session: record,
    summary: {
      recorded_status: record.status, next: "MANUAL_REVIEW_NO_REPLAY", domains: [],
      task_completion: record.status === "COMPLETED" ? "REQUIRES_SUCCESS_WITNESS" : "NOT_ESTABLISHED",
    },
  });
  function response(value: unknown, headers: Record<string, string> = {}) {
    const bytes = JSON.stringify(value);
    return new Response(bytes, { headers: {
      "Content-Length": String(Buffer.byteLength(bytes)),
      "X-Witness-SHA256": createHash("sha256").update(bytes).digest("hex"),
      ...headers,
    } });
  }
  function fetchReplies(...replies: Response[]) {
    const fetch = vi.fn();
    replies.forEach(reply => fetch.mockResolvedValueOnce(reply));
    vi.stubGlobal("fetch", fetch);
    return fetch;
  }

  it.each([404, 503])("keeps the completed session and its Witness independent from investigation %s", async status => {
    const fetch = fetchReplies(response(capability), response(session), new Response(null, { status }), response(witness));
    const bound = await readAgentSession(session.session_id, () => null);
    expect(bound.session).toEqual(session);
    expect(agentExportKind(bound.session!, false)).toBe("witness");
    await expect(readAgentInvestigation(bound.session!)).rejects.toThrow("GATEWAY_" + status);
    await expect(readAgentWitness(bound.session!)).resolves.toMatchObject({ hash: expect.stringMatching(/^[a-f0-9]{64}$/) });
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      "/effectwitness-product-api/capability", "/effectwitness-product-api/session/" + session.session_id,
      "/effectwitness-product-api/investigation/" + session.session_id, "/effectwitness-product-api/witness/" + session.session_id,
    ]);
    expect(fetch.mock.calls.every(([, init]) => !init.method)).toBe(true);
  });

  it("reconciles an unfinished request by GET and allows only a bound investigation export", async () => {
    const running = { ...session, status: "RUNNING" };
    const fetch = fetchReplies(response({ ...capability, latest: null, blocked: true }), response(running),
      new Response(null, { status: 503 }), response(investigation(running)));
    const pending = vi.fn(() => request);
    const bound = await readAgentSession(null, pending);
    expect(pending).toHaveBeenCalledWith(owner);
    expect(bound).toMatchObject({ session: running, pendingId: request });
    expect(mayStart(bound.capability, true)).toBe(false);
    await expect(readAgentInvestigation(running)).rejects.toThrow("GATEWAY_503");
    expect(agentExportKind(running, false)).toBeNull();
    await expect(readAgentWitness(running)).rejects.toThrow("WITNESS_NOT_AVAILABLE");
    const { report } = await readAgentInvestigation(running);
    expect(report.summary.task_completion).toBe("NOT_ESTABLISHED");
    expect(agentExportKind(running, true)).toBe("investigation");
    expect(fetch.mock.calls.map(([url, init]) => [url, init.method])).toEqual([
      ["/effectwitness-product-api/capability", undefined], ["/effectwitness-product-api/request/" + request, undefined],
      ["/effectwitness-product-api/investigation/" + session.session_id, undefined],
      ["/effectwitness-product-api/investigation/" + session.session_id, undefined],
    ]);
  });

  it("maps only lookup 404 to a missing session or request", async () => {
    fetchReplies(new Response(null, { status: 404 }), response(capability), new Response(null, { status: 404 }));
    await expect(readAgentSession(session.session_id, () => null)).rejects.toThrow("GATEWAY_404");
    await expect(readAgentSession(session.session_id, () => null)).rejects.toThrow("IDENTITY_NOT_FOUND");
  });

  it("rejects mismatched owner, session, request and mode before any investigation", async () => {
    const fetch = fetchReplies(
      response(capability), response({ ...session, owner_id: "2".repeat(32) }),
      response(capability), response({ ...session, session_id: "b".repeat(32) }),
      response({ ...capability, latest: null }), response({ ...session, request_id: "other" }),
      response({ ...capability, mode: mode }),
    );
    await expect(readAgentSession(session.session_id, () => null)).rejects.toThrow("SESSION_IDENTITY");
    await expect(readAgentSession(session.session_id, () => null)).rejects.toThrow("SESSION_IDENTITY");
    await expect(readAgentSession(null, () => request)).rejects.toThrow("SESSION_IDENTITY");
    await expect(readAgentSession(null, () => null)).rejects.toThrow("MODE_UNAVAILABLE");
    expect(fetch.mock.calls.some(([url]) => url.includes("/investigation/"))).toBe(false);
  });

  it("refuses wrong report digest, identity or completion, then accepts a fresh matching report", async () => {
    const running = { ...session, status: "RUNNING" };
    const local = investigation(running);
    fetchReplies(response(local, { "X-Witness-SHA256": "0".repeat(64) }),
      response(investigation({ ...running, request_id: "other" })),
      response({ ...local, summary: { ...local.summary, task_completion: "REQUIRES_SUCCESS_WITNESS" } }),
      response(local));
    await expect(readAgentInvestigation(running)).rejects.toThrow("WITNESS_HASH_MISMATCH");
    await expect(readAgentInvestigation(running)).rejects.toThrow("EVIDENCE_IDENTITY");
    await expect(readAgentInvestigation(running)).rejects.toThrow("INVESTIGATION_FORMAT");
    await expect(readAgentInvestigation(running)).resolves.toMatchObject({ report: local });
  });

  it("requires length, digest and original session identity to export a Witness", async () => {
    fetchReplies(response(witness, { "Content-Length": "1" }),
      response(witness, { "X-Witness-SHA256": "0".repeat(64) }),
      response({ ...witness, session: { ...session, owner_id: "2".repeat(32) } }), response(witness));
    await expect(readAgentWitness(session)).rejects.toThrow("WITNESS_SIZE");
    await expect(readAgentWitness(session)).rejects.toThrow("WITNESS_HASH_MISMATCH");
    await expect(readAgentWitness(session)).rejects.toThrow("EVIDENCE_IDENTITY");
    await expect(readAgentWitness(session)).resolves.toMatchObject({ hash: expect.stringMatching(/^[a-f0-9]{64}$/) });
  });

  it.each([200, 503])("discards a late investigation %s after a newer session publishes", async status => {
    const next = { ...session, session_id: "c".repeat(32) };
    const nextReport = investigation(next);
    let finishOld!: (result: Response) => void;
    const oldResponse = new Promise<Response>(resolve => { finishOld = resolve; });
    const fetch = vi.fn().mockReturnValueOnce(oldResponse).mockResolvedValueOnce(response(nextReport));
    vi.stubGlobal("fetch", fetch);
    const publish = vi.fn();
    let activeSession = session.session_id;
    const old = publishInvestigation(session, () => activeSession === session.session_id, publish);
    activeSession = next.session_id;
    await publishInvestigation(next, () => activeSession === next.session_id, publish);
    finishOld(status === 200 ? response(investigation(session)) : new Response(null, { status }));
    await old;
    expect(publish.mock.calls).toEqual([[{ state: "ready", report: nextReport }]]);
  });
});
