export type Domain = "order" | "ops";
export const PREFIX = "/effectwitness-api";
export const TERMINAL = new Set(["COMPLETED", "CANCELLED", "INCONCLUSIVE", "ERROR", "RECONCILE_REQUIRED"]);
export type RecordValue = Record<string, unknown>;
export type LabEvent = { seq: number; event_id: string; observed_at: string; type: string; facts: RecordValue };
export type Bundle = {
  schema_version: "rpf-effect-witness-v2"; domain: Domain;
  contracts: RecordValue; claims: Record<string, string>;
  observation: { state_diff?: unknown; effect: RecordValue; fault: RecordValue; feedback: RecordValue;
    authority_before: { data: RecordValue }; authority_after: { data: RecordValue }; cleanup: RecordValue;
    reconciliation: RecordValue; tool_calls: RecordValue[] };
};
export type Session = {
  schema_version: "rpf-lab-v1"; session_id: string; domain: Domain; run_id: string; request_id: string;
  source: "LIVE_LOCAL_SIMULATION"; status: string; contracts: RecordValue; events: LabEvent[];
  result: Bundle | null; usage: RecordValue | null; error_code: string | null; cancel_requested: boolean;
  witness: { status: "CONTENT_CHECKED_LOCAL"; sha256: string; bytes: number; issuer_authenticity: "NOT_ESTABLISHED"; external_anchor: false } | null;
};
export type Capability = { schema_version: "rpf-lab-v1"; domains: Domain[]; enabled: boolean;
  remaining_reservations: number; limits: RecordValue; explorer: "NOT_IMPLEMENTED" };

export class LabApiError extends Error { constructor(public code: string) { super(code); } }
const obj = (v: unknown): v is RecordValue => v !== null && typeof v === "object" && !Array.isArray(v);
export function parseSession(v: unknown, expectedId?: string): Session {
  if (!obj(v) || v.schema_version !== "rpf-lab-v1" || !/^session-[a-f0-9]{32}$/.test(String(v.session_id)) ||
      (expectedId && v.session_id !== expectedId) || !["order", "ops"].includes(String(v.domain)) ||
      v.source !== "LIVE_LOCAL_SIMULATION" || typeof v.run_id !== "string" || !obj(v.contracts) ||
      !["ACCEPTED", "RUNNING", "CANCEL_REQUESTED", ...TERMINAL].includes(String(v.status)) ||
      !Array.isArray(v.events) || !v.events.every((e, i) => obj(e) && e.seq === i + 1 && typeof e.event_id === "string" && typeof e.type === "string" && obj(e.facts))) {
    throw new LabApiError("INVALID_SESSION_DTO");
  }
  if (v.status === "COMPLETED") {
    if (!obj(v.result) || v.result.schema_version !== "rpf-effect-witness-v2" || v.result.domain !== v.domain ||
        !obj(v.result.observation) || !obj(v.result.claims) || !obj(v.witness) ||
        v.witness.status !== "CONTENT_CHECKED_LOCAL" || v.witness.external_anchor !== false ||
        v.witness.issuer_authenticity !== "NOT_ESTABLISHED" || !/^[a-f0-9]{64}$/.test(String(v.witness.sha256))) {
      throw new LabApiError("INVALID_WITNESS_DTO");
    }
    const o = v.result.observation;
    const claims = v.result.claims;
    const c = v.result.contracts;
    if (!obj(c) || !obj(c.experiment) || c.experiment.run_id !== v.run_id || c.experiment.domain !== v.domain ||
        JSON.stringify(c) !== JSON.stringify(v.contracts) ||
        !["CONTRACT_SATISFIED_IN_RUN", "VIOLATION_CONFIRMED", "INCONCLUSIVE"].includes(String(claims.contract_outcome)) ||
        claims.fault_activation !== "TRIGGERED" || claims.attribution_strength !== "CORRELATIONAL_ONLY" || claims.reproduction !== "NOT_TESTED" ||
        !obj(o.effect) || !obj(o.fault) || !obj(o.feedback) || !obj(o.authority_before) || !obj(o.authority_after) ||
        !obj(o.authority_before.data) || !obj(o.authority_after.data) || !Array.isArray(o.tool_calls) || !obj(o.cleanup) || !obj(o.reconciliation)) {
      throw new LabApiError("INVALID_WITNESS_DTO");
    }
  } else if (v.result !== null || v.witness !== null) throw new LabApiError("UNVERIFIED_RESULT");
  return v as unknown as Session;
}
async function request(path: string, options: RequestInit = {}): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6000);
  try {
    const response = await fetch(PREFIX + path, { ...options, signal: controller.signal, cache: "no-store", credentials: "omit" });
    if (!response.headers.get("Content-Type")?.startsWith("application/json")) throw new LabApiError("GATEWAY_UNAVAILABLE");
    const value: unknown = await response.json();
    if (!response.ok) throw new LabApiError(obj(value) && typeof value.error_code === "string" ? value.error_code : "GATEWAY_UNAVAILABLE");
    return value;
  } catch (e) { if (e instanceof LabApiError) throw e; throw new LabApiError("GATEWAY_UNAVAILABLE"); }
  finally { clearTimeout(timer); }
}
export async function capabilities(): Promise<Capability> {
  const value = await request("/capabilities");
  if (!obj(value) || value.schema_version !== "rpf-lab-v1" || value.explorer !== "NOT_IMPLEMENTED" ||
      !Array.isArray(value.domains) || value.domains.join(",") !== "order,ops" || typeof value.enabled !== "boolean" ||
      !Number.isInteger(value.remaining_reservations) || !obj(value.limits)) throw new LabApiError("INVALID_CAPABILITY_DTO");
  return value as unknown as Capability;
}
export async function startSession(domain: Domain, requestId: string): Promise<Session> {
  return parseSession(await request("/sessions", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domain, mode: "LOCAL_CONTROLLED_CAPTURE", request_id: requestId }) }));
}
export async function getSession(id: string) { return parseSession(await request("/sessions/" + encodeURIComponent(id)), id); }
export async function cancelSession(id: string) { return parseSession(await request("/sessions/" + encodeURIComponent(id) + "/cancel", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }), id); }
export async function witnessBytes(session: Session): Promise<Uint8Array> {
  if (!session.witness || session.status !== "COMPLETED") throw new LabApiError("NO_VALID_WITNESS");
  const response = await fetch(PREFIX + "/sessions/" + encodeURIComponent(session.session_id) + "/witness", { cache: "no-store", credentials: "omit" });
  if (!response.ok) throw new LabApiError("WITNESS_UNAVAILABLE");
  const raw = new Uint8Array(await response.arrayBuffer());
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", raw))).map(x => x.toString(16).padStart(2, "0")).join("");
  if (raw.byteLength !== session.witness.bytes || hash !== session.witness.sha256) throw new LabApiError("WITNESS_HASH_MISMATCH");
  return raw;
}
