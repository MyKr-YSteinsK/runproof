import normalArtifact from "../../../runtime/reviewed-normal-run-v2.json";
import responseLostArtifact from "../../../runtime/reviewed-response-lost-run-v2.json";

export const ACTIVE_SCHEMA_VERSION = "rpf-run-evidence-v2";

export type JsonRecord = Record<string, unknown>;
export type EvidenceLayer = "Observed Fact" | "Verified Result" | "Derived Value" | "Inference" | "AI Analysis";

export interface TrajectoryEvent {
  eventId: string;
  sequence: number;
  eventType: string;
  evidenceLayer: EvidenceLayer;
  entityRefs: Record<string, string>;
  payload: JsonRecord;
}

export interface StateDiffRow {
  path: string;
  before: unknown;
  after: unknown;
  changed: boolean;
}

export interface RunEvidence {
  schemaVersion: string;
  artifactKind: string;
  run: {
    runId: string;
    evaluationId: string;
    startedAt: string;
    endedAt: string;
    durationMs: number;
    agent: JsonRecord;
    scenario: JsonRecord;
    verifier: JsonRecord;
    runtime: JsonRecord;
  };
  llmProvider: JsonRecord;
  environmentProvider: JsonRecord;
  environment: JsonRecord;
  scenario: JsonRecord;
  fault: {
    faultId: string;
    planned: boolean;
    triggered: boolean;
    observed: boolean;
    reconciled: boolean;
  };
  trajectoryContract: JsonRecord;
  trajectory: TrajectoryEvent[];
  verification: {
    verifierId: string;
    verifierVersion: string;
    expectedState: JsonRecord;
    initialState: JsonRecord;
    actualState: JsonRecord;
    stateDiff: StateDiffRow[];
    checks: Record<string, boolean>;
    violatedInvariants: string[];
    passed: boolean;
    evidence: JsonRecord;
  };
  outcome: {
    status: string;
    source: string;
    agentQualityEligible: boolean;
    formalRunStarted: boolean;
  };
  runtimeBudget: JsonRecord;
}

const asObject = (value: unknown, label: string): JsonRecord => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Malformed evidence: ${label}`);
  }
  return value as JsonRecord;
};

const asString = (value: unknown, label: string): string => {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Malformed evidence: ${label}`);
  }
  return value;
};

const asNumber = (value: unknown, label: string): number => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Malformed evidence: ${label}`);
  }
  return value;
};

const asBoolean = (value: unknown, label: string): boolean => {
  if (typeof value !== "boolean") {
    throw new Error(`Malformed evidence: ${label}`);
  }
  return value;
};

const asArray = (value: unknown, label: string): unknown[] => {
  if (!Array.isArray(value)) {
    throw new Error(`Malformed evidence: ${label}`);
  }
  return value;
};

const normalizeEvent = (raw: unknown): TrajectoryEvent => {
  const item = asObject(raw, "trajectory event");
  const payload = { ...item };
  delete payload.event_id;
  delete payload.sequence;
  delete payload.event_type;
  delete payload.evidence_layer;
  delete payload.entity_refs;
  return {
    eventId: asString(item.event_id, "trajectory event_id"),
    sequence: asNumber(item.sequence, "trajectory sequence"),
    eventType: asString(item.event_type, "trajectory event_type"),
    evidenceLayer: asString(item.evidence_layer, "trajectory evidence_layer") as EvidenceLayer,
    entityRefs: asObject(item.entity_refs, "trajectory entity_refs") as Record<string, string>,
    payload,
  };
};

export const normalizeArtifact = (raw: unknown): RunEvidence => {
  const artifact = asObject(raw, "artifact");
  const schemaVersion = asString(artifact.schema_version, "schema_version");
  if (schemaVersion !== ACTIVE_SCHEMA_VERSION) {
    throw new Error(`Unsupported active evidence schema: ${schemaVersion}`);
  }
  const run = asObject(artifact.run, "run");
  const runtime = asObject(run.runtime, "run.runtime");
  const verification = asObject(artifact.verification, "verification");
  const outcome = asObject(artifact.outcome, "outcome");
  const fault = asObject(artifact.fault, "fault");
  return {
    schemaVersion,
    artifactKind: asString(artifact.artifact_kind, "artifact_kind"),
    run: {
      runId: asString(run.run_id, "run.run_id"),
      evaluationId: asString(run.evaluation_id, "run.evaluation_id"),
      startedAt: asString(run.started_at, "run.started_at"),
      endedAt: asString(run.ended_at, "run.ended_at"),
      durationMs: asNumber(artifact.duration_ms, "duration_ms"),
      agent: asObject(run.agent, "run.agent"),
      scenario: asObject(run.scenario, "run.scenario"),
      verifier: asObject(run.verifier, "run.verifier"),
      runtime,
    },
    llmProvider: asObject(artifact.llm_provider, "llm_provider"),
    environmentProvider: asObject(artifact.environment_provider, "environment_provider"),
    environment: asObject(artifact.environment, "environment"),
    scenario: asObject(artifact.scenario, "scenario"),
    fault: {
      faultId: asString(fault.fault_id, "fault.fault_id"),
      planned: asBoolean(fault.planned, "fault.planned"),
      triggered: asBoolean(fault.triggered, "fault.triggered"),
      observed: asBoolean(fault.observed, "fault.observed"),
      reconciled: asBoolean(fault.reconciled, "fault.reconciled"),
    },
    trajectoryContract: asObject(artifact.trajectory_contract, "trajectory_contract"),
    trajectory: asArray(artifact.trajectory, "trajectory").map(normalizeEvent),
    verification: {
      verifierId: asString(verification.verifier_id, "verification.verifier_id"),
      verifierVersion: asString(verification.verifier_version, "verification.verifier_version"),
      expectedState: asObject(verification.expected_state, "verification.expected_state"),
      initialState: asObject(verification.initial_state, "verification.initial_state"),
      actualState: asObject(verification.actual_state, "verification.actual_state"),
      stateDiff: asArray(verification.state_diff, "verification.state_diff").map((row) => {
        const value = asObject(row, "verification.state_diff row");
        return {
          path: asString(value.path, "verification.state_diff.path"),
          before: value.before,
          after: value.after,
          changed: asBoolean(value.changed, "verification.state_diff.changed"),
        };
      }),
      checks: Object.fromEntries(
        Object.entries(asObject(verification.checks, "verification.checks")).map(([key, value]) => [key, asBoolean(value, `verification.checks.${key}`)]),
      ),
      violatedInvariants: asArray(verification.violated_invariants, "verification.violated_invariants").map((value) => asString(value, "violated invariant")),
      passed: asBoolean(verification.passed, "verification.passed"),
      evidence: asObject(verification.evidence, "verification.evidence"),
    },
    outcome: {
      status: asString(outcome.status, "outcome.status"),
      source: asString(outcome.source, "outcome.source"),
      agentQualityEligible: asBoolean(outcome.agent_quality_eligible, "outcome.agent_quality_eligible"),
      formalRunStarted: asBoolean(outcome.formal_run_started, "outcome.formal_run_started"),
    },
    runtimeBudget: asObject(artifact.runtime_budget, "runtime_budget"),
  };
};

export const reviewedRuns: RunEvidence[] = [normalizeArtifact(normalArtifact), normalizeArtifact(responseLostArtifact)];

export const getRun = (runId: string): RunEvidence | undefined => reviewedRuns.find((run) => run.run.runId === runId);

export const isFaultedRun = (run: RunEvidence): boolean => run.fault.planned && run.fault.triggered;

export const getUsage = (run: RunEvidence): JsonRecord => asObject(run.llmProvider.raw_usage, "llm_provider.raw_usage");

export const getDerivedCost = (run: RunEvidence): JsonRecord => asObject(run.llmProvider.derived_cost, "llm_provider.derived_cost");
