import { productApi } from "./productLocalApi";

export const agentMode = "OFFLINE_REFERENCE_AGENT";
export type AgentCapability = {
  mode: string; remaining: number; blocked: boolean; provider_reservations: number;
  latest: string | null; profile: string; tools: string[];
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
  session_id: string; mode: string; profile: string; status: string; provider_reservations: number;
  candidates: Candidate[]; source: Record<string, string>; events: AgentEvent[];
  rounds: { domain: string; before: Snapshot; after: Snapshot; tool_status: string; fault: Record<string, boolean>;
    outcome: { contract_outcome: string }; feedback: { sha256: string } }[];
};
async function get<T>(route: string, body?: object): Promise<T> {
  const response = await fetch("/effectwitness-product-api" + route, {
    cache: "no-store", signal: AbortSignal.timeout(12000),
    ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) throw Error("GATEWAY_" + response.status);
  return response.json() as Promise<T>;
}
export const agentApi = {
  capability: () => get<AgentCapability>("/capability"),
  session: (id: string) => get<AgentSession>("/session/" + encodeURIComponent(id)),
  request: (id: string) => get<AgentSession>("/request/" + encodeURIComponent(id)),
  start: (id: string) => get<AgentSession>("/session", { mode: agentMode, request_id: id }),
  witness: productApi.witness,
};
export function mayStart(cap: AgentCapability | null, pending: boolean) {
  return cap?.mode === agentMode && cap.provider_reservations === 0 && cap.remaining === 1
    && cap.blocked === false && cap.latest === null && !pending;
}
