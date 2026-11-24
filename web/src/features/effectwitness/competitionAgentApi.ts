import { productApi, requestLocalProduct } from "./productLocalApi";

export const agentMode = "OFFLINE_REFERENCE_AGENT";
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
