import { productApi, requestLocalProduct } from "./productLocalApi";

export const agentMode = "OFFLINE_REFERENCE_AGENT";
export const investigationSchema = "runproof-agent-investigation/v2";
const legacyInvestigationSchema = "runproof-agent-investigation/v1";
const witnessSchema = "runproof-competition-agent-witness/v2";
export type AgentCapability = {
  mode: string; remaining: number; blocked: boolean; provider_reservations: number;
  instance: string | null; owner: string; readonly: boolean; version: string; latest: string | null; profile: string; tools: string[];
};
type Intent = { candidate_id: string; tool: string; action_id: string; input_feedback_sha256: string | null };
type EventData = {
  intent?: Intent | null; verdict?: string; domain?: string; reason?: string;
  input_feedback_sha256?: string | null; sha256?: string; after_sha256?: string; status?: string;
};
export type AgentEvent = { seq: number; kind: string; origin: string; data: EventData; sha256: string };
type Candidate = {
  candidate: string; sha256: string; execution: Record<string, unknown>;
  effect: Record<string, unknown>; experiment: Record<string, unknown>;
};
type Snapshot = { order?: Record<string, unknown>; config?: Record<string, unknown>; receipts: unknown[] };
export type AgentSession = {
  owner_id?: string; request_id?: string; session_id: string; mode: string; profile: string; status: string; provider_reservations: number;
  candidates: Candidate[]; source: Record<string, string>; events: AgentEvent[];
  rounds: { domain: string; before: Snapshot; after: Snapshot; tool_status: string; fault: Record<string, boolean>;
    outcome: { contract_outcome: string }; feedback: { sha256: string } }[];
};
export type AgentInvestigation = {
  schema: string;
  issuer: string;
  session: AgentSession;
  summary: {
    next: string;
    task_completion: string;
    recorded_status?: string;
    domains: {
      domain: string;
      effect: string;
      gaps: string[];
      fault: Partial<Record<"planned" | "triggered" | "observed" | "agent_exposed", boolean | null>>;
    }[];
  };
};
async function requestAgentJson<T>(route: string, init?: RequestInit): Promise<T> {
  const response = await requestLocalProduct(route, init);
  return response.json();
}
export const agentApi = {
  capability: () => requestAgentJson<AgentCapability>("/capability"),
  session: (id: string) => requestAgentJson<AgentSession>("/session/" + encodeURIComponent(id)),
  request: (id: string) => requestAgentJson<AgentSession>("/request/" + encodeURIComponent(id)),
  start: (id: string, owner?: string) => requestAgentJson<AgentSession>("/session", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: agentMode, request_id: id, owner_id: owner }),
  }),
  witness: productApi.witness,
  investigation: (id: string) => productApi.witness(id, "investigation"),
};
export function mayStart(cap: AgentCapability | null, pending: boolean) {
  return !!cap?.instance && !cap.readonly && cap.mode === agentMode && cap.provider_reservations === 0 && cap.remaining === 1
    && cap.blocked === false && cap.latest === null && !pending;
}

export async function readAgentSession(requested: string | null, pendingForOwner: (owner: string) => string | null) {
  const capability = await agentApi.capability();
  if (capability.mode !== agentMode || capability.provider_reservations !== 0) throw Error("MODE_UNAVAILABLE");
  const pendingId = capability.instance ? pendingForOwner(capability.instance) : null;
  const sessionId = requested || capability.latest;
  if (!sessionId && !pendingId) return { capability, session: null, pendingId };

  let session: AgentSession;
  try {
    session = sessionId ? await agentApi.session(sessionId) : await agentApi.request(pendingId!);
  } catch (error) {
    if (error instanceof Error && error.message === "GATEWAY_404") throw Error("IDENTITY_NOT_FOUND");
    throw error;
  }
  if (!session?.session_id || !session.request_id || !capability.instance || session.owner_id !== capability.instance
      || session.mode !== agentMode || session.provider_reservations !== 0
      || (sessionId ? session.session_id !== sessionId : session.request_id !== pendingId)) {
    throw Error("SESSION_IDENTITY");
  }
  return { capability, session, pendingId };
}

function boundEvidence<T extends { session: AgentSession }>(bytes: ArrayBuffer, session: AgentSession): T {
  let evidence: T;
  try {
    evidence = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw Error("EVIDENCE_FORMAT");
  }
  const record = evidence?.session;
  if (!record || !session.owner_id || !session.request_id || record.session_id !== session.session_id
      || record.owner_id !== session.owner_id || record.request_id !== session.request_id
      || record.mode !== agentMode || record.provider_reservations !== 0 || record.status !== session.status) {
    throw Error("EVIDENCE_IDENTITY");
  }
  return evidence;
}

export async function readAgentInvestigation(session: AgentSession) {
  const file = await agentApi.investigation(session.session_id);
  const report = boundEvidence<AgentInvestigation>(file.bytes, session);
  const summary = report.summary;
  const completion = session.status === "COMPLETED" ? "REQUIRES_SUCCESS_WITNESS" : "NOT_ESTABLISHED";
  if ((report.schema !== investigationSchema && report.schema !== legacyInvestigationSchema)
      || report.issuer !== "NOT_ESTABLISHED" || typeof summary?.next !== "string"
      || summary.task_completion !== completion || !Array.isArray(summary.domains)
      || (report.schema === investigationSchema && summary.recorded_status !== session.status)
      || !summary.domains.every(domain => typeof domain?.domain === "string" && typeof domain.effect === "string"
        && Array.isArray(domain.gaps) && domain.gaps.every(gap => typeof gap === "string"))) {
    throw Error("INVESTIGATION_FORMAT");
  }
  return { ...file, report };
}

export async function readAgentWitness(session: AgentSession) {
  if (session.status !== "COMPLETED") throw Error("WITNESS_NOT_AVAILABLE");
  const file = await agentApi.witness(session.session_id);
  const witness = boundEvidence<{ schema: string; session: AgentSession }>(file.bytes, session);
  if (witness.schema !== witnessSchema) throw Error("WITNESS_FORMAT");
  return file;
}

export function agentExportKind(session: AgentSession, investigationReady: boolean) {
  if (session.status === "COMPLETED") return "witness";
  return investigationReady ? "investigation" : null;
}
