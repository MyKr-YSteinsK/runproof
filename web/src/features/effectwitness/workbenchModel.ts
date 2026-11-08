import { validateRecordedPayload, type RecordedEvidence } from "./recordedEvidence";

export type Domain = "order" | "ops";

// Never project a report until its embedded source bytes and identity are validated.
export async function loadWorkbenchEvidence(): Promise<RecordedEvidence> {
  return validateRecordedPayload();
}

export function domainFromSearch(search: string): Domain {
  return new URLSearchParams(search).get("domain") === "ops" ? "ops" : "order";
}

export function workbenchHref(search: string, domain: Domain): string {
  const params = new URLSearchParams(search);
  params.set("domain", domain);
  return `/effectwitness/workbench?${params.toString()}`;
}

export function evidenceForDomain(evidence: RecordedEvidence, domain: Domain) {
  if (domain === "ops") {
    return { kind: "HISTORICAL_WITNESS_SAMPLE" as const, witness: evidence.opsWitness, trials: [], events: [] };
  }
  return { kind: "RECORDED_RPF46_SUMMARY" as const, witness: evidence.orderWitness,
    trials: evidence.report.trials, events: evidence.report.feedback_link_events };
}
