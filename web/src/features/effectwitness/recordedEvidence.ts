import manifestText from "../../../../spikes/rpf-47/EVIDENCE_MANIFEST.json?raw";
import reportText from "../../../../spikes/rpf-46/session-report.json?raw";
import orderWitnessText from "../../../../spikes/rpf-43/sample-witness.json?raw";
import opsWitnessText from "../../../../spikes/rpf-44/sample-ops-witness.json?raw";

export const RECORDED_PINS = {
  manifest: "6a9ebe1f1d5a759c8335275dc4a16afbe939ef9aa7eac041756dfd3ec434cdbf",
  report: "f450803b8fd3ec51fe2663ba95370577c92f0eb70cc0dd05f4d7e5b98ab25d15",
  orderWitness: "ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e",
  opsWitness: "21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873",
  sourceCommit: "69dfe3079f5778cf6e569e82cf8382e4e3ec04a8",
} as const;

export interface RecordedEvent {
  seq: number;
  event_id: string;
  type: string;
  observed_at: string;
  facts: Record<string, unknown>;
}

export interface RecordedTrial {
  round: number;
  candidate_id: string;
  effect: { contract_outcome: string; violated_rules: string[]; state_diff: Record<string, { before: unknown; after: unknown }> };
  fault: { activation: string; triggered: boolean; reconciled: boolean };
  reconciliation: { status: string } | null;
  after: { data: { receipts: unknown[] } };
  witness: { status: string; external_anchor: boolean; issuer_authenticity: string; sha256?: string; bytes?: number };
  feedback_sha256: string;
}

export interface RecordedReport {
  schema_version: string;
  scope: string;
  session_id: string;
  source: string;
  created_at: string;
  completed_at: string;
  selections: Array<{ round: number; candidate_id: string; input_feedback_hash: string | null }>;
  trials: RecordedTrial[];
  feedback_link_events: RecordedEvent[];
  usage: { provider_requests: number; physical_trials_completed: number; tokens: number; estimated_cost_cny_upper: number };
  research: { H1: string; L1: boolean; L2: boolean; attribution: string };
  trust: { external_anchor: boolean; issuer_authenticity: string };
}

export interface HistoricalWitness {
  schema_version: string;
  claims: { contract_outcome: string; fault_activation: string; attribution_strength: string; reproduction: string };
}

export interface RecordedEvidence {
  report: RecordedReport;
  orderWitness: HistoricalWitness;
  opsWitness: HistoricalWitness;
  manifest: { source_commit: string; sources: Array<Record<string, unknown>> };
}

export const embeddedRecordedPayload = {
  manifestText,
  reportText,
  orderWitnessText,
  opsWitnessText,
};

async function digest(text: string): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error("WEBCRYPTO_UNAVAILABLE");
  const bytes = new TextEncoder().encode(text.replace(/\r\n/g, "\n"));
  const hash = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function parseJson(text: string, code: string): Record<string, unknown> {
  let parsed: unknown;
  try { parsed = JSON.parse(text); } catch { throw new Error(`${code}_INVALID_JSON`); }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(`${code}_INVALID_SCHEMA`);
  return parsed as Record<string, unknown>;
}

function exactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

export async function validateRecordedPayload(payload = embeddedRecordedPayload): Promise<RecordedEvidence> {
  const [manifestHash, reportHash, orderHash, opsHash] = await Promise.all([
    digest(payload.manifestText), digest(payload.reportText), digest(payload.orderWitnessText), digest(payload.opsWitnessText),
  ]);
  if (manifestHash !== RECORDED_PINS.manifest) throw new Error("MANIFEST_SHA256_MISMATCH");
  if (reportHash !== RECORDED_PINS.report) throw new Error("RPF46_REPORT_SHA256_MISMATCH");
  if (orderHash !== RECORDED_PINS.orderWitness) throw new Error("RPF43_SAMPLE_SHA256_MISMATCH");
  if (opsHash !== RECORDED_PINS.opsWitness) throw new Error("RPF44_SAMPLE_SHA256_MISMATCH");

  const manifest = parseJson(payload.manifestText, "MANIFEST");
  if (!exactKeys(manifest, ["schema_version", "source_branch", "source_commit", "sources", "competition", "validation"]) ||
      manifest.schema_version !== "rpf-47-evidence-manifest-v1" ||
      manifest.source_branch !== "codex/rpf-46-live-pge-lab" ||
      manifest.source_commit !== RECORDED_PINS.sourceCommit || !Array.isArray(manifest.sources) || manifest.sources.length !== 3) {
    throw new Error("MANIFEST_IDENTITY_OR_SCHEMA_MISMATCH");
  }
  const expectedSources = [
    ["rpf46-summary", "RECORDED_RPF46_SUMMARY", "spikes/rpf-46/session-report.json", RECORDED_PINS.report, "rpf46-research-summary-v1"],
    ["rpf43-order-sample", "HISTORICAL_WITNESS_SAMPLE", "spikes/rpf-43/sample-witness.json", RECORDED_PINS.orderWitness, "rpf-effect-witness-v1"],
    ["rpf44-ops-sample", "HISTORICAL_WITNESS_SAMPLE", "spikes/rpf-44/sample-ops-witness.json", RECORDED_PINS.opsWitness, "rpf-effect-witness-v2"],
  ];
  for (const [index, expected] of expectedSources.entries()) {
    const source = manifest.sources[index];
    if (!source || typeof source !== "object" || Array.isArray(source)) throw new Error("MANIFEST_SOURCE_INVALID");
    const item = source as Record<string, unknown>;
    if (item.id !== expected[0] || item.kind !== expected[1] || item.path !== expected[2] || item.sha256 !== expected[3] || item.schema_version !== expected[4]) {
      throw new Error("MANIFEST_SOURCE_IDENTITY_MISMATCH");
    }
  }

  const reportObject = parseJson(payload.reportText, "RPF46_REPORT");
  const report = reportObject as unknown as RecordedReport;
  if (report.schema_version !== "rpf46-research-summary-v1" ||
      report.scope !== "REDACTED_LOCAL_EXECUTION_REPORT_NOT_EXTERNAL_ATTESTATION" ||
      report.session_id !== "exploration-a3cdf741b7e34f4f97c07228fdf9b679" || report.source !== "LIVE_LOCAL_SIMULATION" ||
      !Array.isArray(report.selections) || report.selections.length !== 2 ||
      report.selections[0]?.round !== 1 || report.selections[0]?.candidate_id !== "normal" ||
      report.selections[1]?.round !== 2 || report.selections[1]?.candidate_id !== "response-lost" ||
      !Array.isArray(report.trials) || report.trials.length !== 2 ||
      !Array.isArray(report.feedback_link_events) || report.trust?.external_anchor !== false ||
      report.trust?.issuer_authenticity !== "NOT_ESTABLISHED" || report.research?.attribution !== "CORRELATIONAL_ONLY") {
    throw new Error("RPF46_REPORT_IDENTITY_OR_SCHEMA_MISMATCH");
  }
  const feedback = report.feedback_link_events.find((event) => event.seq === 14 && event.type === "AUTHORITY_FEEDBACK_VALIDATED");
  const inputFreeze = report.feedback_link_events.find((event) => event.seq === 15 && event.type === "PROVIDER_INPUT_FROZEN");
  const secondChoice = report.feedback_link_events.find((event) => event.seq === 16 && event.type === "PROVIDER_SELECTION_ACCEPTED");
  const feedbackHash = feedback?.facts?.feedback_sha256;
  if (!feedback || !inputFreeze || !secondChoice || typeof feedbackHash !== "string" ||
      feedbackHash !== report.selections[1].input_feedback_hash || !(feedback.seq < inputFreeze.seq && inputFreeze.seq < secondChoice.seq)) {
    throw new Error("RPF46_FEEDBACK_CHAIN_MISMATCH");
  }
  for (const [index, trial] of report.trials.entries()) {
    if (trial.round !== index + 1 || trial.effect?.contract_outcome !== "CONTRACT_SATISFIED_IN_RUN" ||
        !Array.isArray(trial.effect.violated_rules) || trial.effect.violated_rules.length !== 0 ||
        !Array.isArray(trial.after?.data?.receipts) || trial.after.data.receipts.length !== 1) {
      throw new Error("RPF46_TRIAL_FACTS_MISMATCH");
    }
  }
  const secondTrial = report.trials[1];
  if (secondTrial.fault?.activation !== "TRIGGERED" || !secondTrial.fault.triggered || !secondTrial.fault.reconciled ||
      secondTrial.reconciliation?.status !== "RECONCILED_COMMITTED" || secondTrial.witness?.status !== "CONTENT_CHECKED_LOCAL" ||
      secondTrial.witness.external_anchor !== false || secondTrial.witness.issuer_authenticity !== "NOT_ESTABLISHED" ||
      report.usage?.provider_requests !== 2 || report.usage?.physical_trials_completed !== 2 || report.usage?.tokens !== 1612) {
    throw new Error("RPF46_OUTCOME_OR_TRUST_LIMIT_MISMATCH");
  }

  const orderObject = parseJson(payload.orderWitnessText, "RPF43_SAMPLE");
  const opsObject = parseJson(payload.opsWitnessText, "RPF44_SAMPLE");
  const orderWitness = orderObject as unknown as HistoricalWitness;
  const opsWitness = opsObject as unknown as HistoricalWitness;
  for (const [sample, schema] of [[orderWitness, "rpf-effect-witness-v1"], [opsWitness, "rpf-effect-witness-v2"]] as const) {
    if (sample.schema_version !== schema || sample.claims?.contract_outcome !== "CONTRACT_SATISFIED_IN_RUN" ||
        sample.claims?.fault_activation !== "TRIGGERED" || sample.claims?.attribution_strength !== "CORRELATIONAL_ONLY" ||
        sample.claims?.reproduction !== "NOT_TESTED") throw new Error("HISTORICAL_SAMPLE_CLAIM_MISMATCH");
  }
  return { report, orderWitness, opsWitness, manifest: manifest as unknown as RecordedEvidence["manifest"] };
}
