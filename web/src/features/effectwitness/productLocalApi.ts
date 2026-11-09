const base = "/effectwitness-product-api";
export const mode = "CONTROLLED_LOCAL_PRODUCT";

export type Capability = { mode: string; remaining: number; blocked: boolean; provider_reservations: number; latest: string | null };
type Event = { seq: number; kind: string; domain: string | null };
type Round = {
  domain: "order" | "ops"; contract_sha256: string; tool_status: string; authority: string;
  before: { receipts: unknown[] }; after: { receipts: unknown[] };
  fault: Record<"planned" | "triggered" | "observed" | "agent_exposed", boolean>;
  outcome: { contract_outcome: string; verifier_id: string; state_diff: unknown };
  feedback: unknown; feedback_sha256: string;
};
export type Session = {
  session_id: string; status: string; provider_reservations: number;
  candidates: { candidate: string; sha256: string }[]; rounds: Round[]; events: Event[];
  selection: { decision: string; reason: string; policy_id: string; input_feedback_sha256: string | null;
    selected_candidate_contract_sha256: string | null } | null;
  limits: unknown; cleanup: string;
};

async function request(path: string, init?: RequestInit) {
  const response = await fetch(base + path, { ...init, cache: "no-store", signal: AbortSignal.timeout(12000) });
  if (!response.ok) throw new Error(`GATEWAY_${response.status}`);
  return response;
}

export const productApi = {
  capability: async (): Promise<Capability> => (await request("/capability")).json(),
  session: async (id: string): Promise<Session> => (await request("/session/" + encodeURIComponent(id))).json(),
  readRequest: async (id: string): Promise<Session> => (await request("/request/" + encodeURIComponent(id))).json(),
  create: async (id: string): Promise<Session> => (await request("/session", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, request_id: id }),
  })).json(),
  witness: async (id: string) => {
    const response = await request("/witness/" + encodeURIComponent(id));
    const length = Number(response.headers.get("Content-Length"));
    if (!Number.isInteger(length) || length < 1 || length > 65536) throw new Error("WITNESS_SIZE");
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength !== length) throw new Error("WITNESS_SIZE");
    const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
      .map(byte => byte.toString(16).padStart(2, "0")).join("");
    if (hash !== response.headers.get("X-Witness-SHA256")) throw new Error("WITNESS_HASH_MISMATCH");
    return { bytes, hash };
  },
};
