import { request, LabApiError } from "./labApi";

type Obj = Record<string, unknown>;
const obj = (v: unknown): v is Obj => v !== null && typeof v === "object" && !Array.isArray(v);
const hex = (v: unknown) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
export const LIVE_TERMINAL = new Set(["COMPLETED", "CANCELLED", "RECONCILE_REQUIRED", "ERROR", "INCONCLUSIVE"]);
export type LiveCapability = { explorer: string; enabled: boolean; busy: boolean; remaining_sessions: number;
  requested_model: string; limits: Obj; physical_trials: number };
export type LiveTrial = { schema_version: string; round: number; candidate_id: string; run_id: string; plan_digest: string;
  contracts: { effect: Obj }; observation: { effect: { state_diff: Record<string, {before: unknown; after: unknown}> };
    fault: Obj; authority_before: {sha256: string; data: Obj}; authority_after: {sha256: string; data: Obj};
    reconciliation: unknown; cleanup: Obj }; claims: Record<string, string>; feedback: Obj; feedback_sha256: string;
  new_facts: string[]; witness: { status: string; external_anchor: false; issuer_authenticity: "NOT_ESTABLISHED"; sha256?: string; bytes?: number } };
export type LiveSession = { schema_version: string; session_id: string; request_id: string; status: string; run_outcome: string;
  source: string; explorer: string; target_driver: string; rationale: string; plan_digest: string; plan: Obj;
  error_code: string | null; cancel_requested: boolean; selections: {round: number; candidate_id: string; tool_call_id: string;
    response_id: string; input_messages_hash: string; input_feedback_hash: string | null}[];
  trials: LiveTrial[]; usage: Obj; provider_requests: Obj[]; research: {L1: boolean; L2: boolean; H1: string; attribution: string};
  events: {seq: number; event_id: string; type: string; observed_at: string; facts: Obj}[] };

export function parseLive(v: unknown, id?: string): LiveSession {
  if (!obj(v) || v.schema_version !== "rpf-lab-exploration-v1" || !/^exploration-[a-f0-9]{32}$/.test(String(v.session_id)) ||
      (id && id !== v.session_id) || v.source !== "LIVE_LOCAL_SIMULATION" || v.explorer !== "LIVE_EXPLORER_DEEPSEEK" ||
      v.target_driver !== "DETERMINISTIC_CONTROLLED_TARGET" || v.rationale !== "RATIONALE_NOT_RECORDED" ||
      !["ACCEPTED", "RUNNING", "CANCEL_REQUESTED", ...LIVE_TERMINAL].includes(String(v.status)) ||
      !hex(v.plan_digest) || !obj(v.plan) || v.plan.session_id !== v.session_id || !obj(v.usage) || !obj(v.research) ||
      !Array.isArray(v.selections) || v.selections.length > 2 || !Array.isArray(v.trials) || v.trials.length > 2 ||
      !Array.isArray(v.events) || !v.events.every((e,i) => obj(e) && e.seq === i+1 && obj(e.facts) && typeof e.event_id === "string") ||
      !Array.isArray(v.provider_requests)) throw new LabApiError("INVALID_EXPLORATION_DTO");
  for (const [i, t] of v.trials.entries()) {
    if (!obj(t) || t.schema_version !== "rpf-lab-trial-v1" || t.round !== i+1 || t.plan_digest !== v.plan_digest ||
        !["normal", "planned-untriggered", "response-lost"].includes(String(t.candidate_id)) ||
        !obj(t.contracts) || !obj(t.contracts.effect) || !obj(t.contracts.experiment) || t.contracts.experiment.run_id !== t.run_id ||
        !obj(t.observation) || !obj(t.observation.effect) || !obj(t.observation.effect.state_diff) || !obj(t.observation.fault) ||
        !obj(t.observation.authority_before) || !obj(t.observation.authority_after) || !obj(t.observation.cleanup) ||
        !obj(t.feedback) || !hex(t.feedback_sha256) || !Array.isArray(t.new_facts) || !obj(t.claims) ||
        !obj(t.witness) || t.witness.external_anchor !== false || t.witness.issuer_authenticity !== "NOT_ESTABLISHED" ||
        t.witness.status !== (t.candidate_id === "response-lost" ? "CONTENT_CHECKED_LOCAL" : "NOT_ISSUED_PROFILE_NOT_ELIGIBLE") ||
        (t.witness.status === "CONTENT_CHECKED_LOCAL" && (!hex(t.witness.sha256) || !Number.isInteger(t.witness.bytes)))) {
      throw new LabApiError("INVALID_TRIAL_EVIDENCE_DTO");
    }
    const choice = v.selections[i];
    if (!obj(choice) || choice.round !== i+1 || choice.candidate_id !== t.candidate_id || typeof choice.tool_call_id !== "string" ||
        !hex(choice.input_messages_hash) || (i === 1 && choice.input_feedback_hash !== (v.trials[0] as Obj).feedback_sha256))
      throw new LabApiError("INVALID_FEEDBACK_LINK");
  }
  if (v.status === "COMPLETED" && (v.trials.length !== 2 || v.selections.length !== 2 || v.usage.usage_known !== true))
    throw new LabApiError("INCOMPLETE_EXPLORATION_SUCCESS");
  return v as unknown as LiveSession;
}
export async function liveCapabilities(): Promise<LiveCapability> {
  const v = await request("/explorations/capabilities");
  if (!obj(v) || v.schema_version !== "rpf-lab-exploration-v1" || !["AVAILABLE", "KEY_MISSING", "DISABLED", "UNAVAILABLE"].includes(String(v.explorer)) ||
      typeof v.enabled !== "boolean" || typeof v.busy !== "boolean" || !Number.isInteger(v.remaining_sessions) || !obj(v.limits))
    throw new LabApiError("INVALID_EXPLORATION_CAPABILITY");
  return v as unknown as LiveCapability;
}
export async function startLive(requestId: string) { return parseLive(await request("/explorations", { method: "POST",
  headers: {"Content-Type":"application/json"}, body: JSON.stringify({mode:"PGE_LIVE_ORDER", domain:"order", request_id:requestId}) })); }
export async function getLive(id: string) { return parseLive(await request("/explorations/"+encodeURIComponent(id)), id); }
export async function cancelLive(id: string) { return parseLive(await request("/explorations/"+encodeURIComponent(id)+"/cancel", {
  method:"POST", headers:{"Content-Type":"application/json"}, body:"{}" }), id); }
export async function liveWitness(s: LiveSession, t: LiveTrial): Promise<Uint8Array> {
  if (t.witness.status !== "CONTENT_CHECKED_LOCAL") throw new LabApiError("WITNESS_NOT_ISSUED");
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 6000);
  try {
    const r = await fetch(`/effectwitness-api/explorations/${s.session_id}/witness/${t.round}`, {cache:"no-store", credentials:"omit", signal:controller.signal});
    if (!r.ok) throw new LabApiError("WITNESS_UNAVAILABLE");
    const raw = new Uint8Array(await r.arrayBuffer());
    const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", raw))].map(x=>x.toString(16).padStart(2,"0")).join("");
    if (raw.byteLength !== t.witness.bytes || sha !== t.witness.sha256) throw new LabApiError("WITNESS_HASH_MISMATCH");
    return raw;
  } finally { clearTimeout(timer); }
}
