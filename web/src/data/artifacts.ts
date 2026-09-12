import normalArtifact from "../../../runtime/reviewed-normal-run-v2.json";
import responseLostArtifact from "../../../runtime/reviewed-response-lost-run-v2.json";
import agentFailArtifact from "../../../runtime/reviewed-agent-fail-run.json";
import environmentErrorArtifact from "../../../runtime/reviewed-environment-error-run.json";
import reproductionArtifact from "../../../runtime/reviewed-agent-fail-reproduction-run.json";
import failureCaseArtifact from "../../../runtime/reviewed-failure-case.json";
import promotedFailureCaseArtifact from "../../../runtime/reviewed-failure-case-promoted.json";
import regressionStabilityOneArtifact from "../../../runtime/reviewed-regression-stability-01-run.json";
import regressionStabilityTwoArtifact from "../../../runtime/reviewed-regression-stability-02-run.json";
import regressionFixedCandidateArtifact from "../../../runtime/reviewed-regression-fixed-candidate-run.json";
import regressionArtifact from "../../../runtime/reviewed-regression.json";
import regressionCollectionArtifact from "../../../runtime/reviewed-regression-collection.json";
import regressionKnownBadResultArtifact from "../../../runtime/reviewed-regression-known-bad-result.json";
import regressionFixedCandidateResultArtifact from "../../../runtime/reviewed-regression-fixed-candidate-result.json";

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
  } | null;
  outcome: {
    status: string;
    source: string;
    agentQualityEligible: boolean;
    formalRunStarted: boolean;
    reason?: string;
    attribution?: string;
    agentStarted?: boolean;
  };
  runtimeBudget: JsonRecord;
  failureAttribution: JsonRecord | null;
  healthContext: JsonRecord | null;
}

export interface FailureCase {
  schemaVersion: string;
  artifactKind: string;
  failureCase: {
    failureCaseId: string;
    createdAt: string;
    updatedAt: string;
    workflowState: string;
    currentStatus: string;
    isRegression: boolean;
    regressionStatus: string;
  };
  sourceRun: JsonRecord & { runId: string; environmentId: string };
  agent: JsonRecord;
  scenario: JsonRecord;
  classification: JsonRecord;
  failureSignature: {
    signatureVersion: string;
    value: string;
    components: JsonRecord;
  };
  failureObservation: JsonRecord;
  evidenceRefs: JsonRecord[];
  reproductionAttempts: Array<JsonRecord & { runId: string; environmentId: string; status: string }>;
  validation: JsonRecord | null;
  regression: JsonRecord;
  promotion: JsonRecord | null;
}

export interface Regression {
  schemaVersion: string;
  artifactKind: string;
  regression: {
    regressionId: string;
    regressionVersion: string;
    createdAt: string;
    updatedAt: string;
    lifecycleStatus: string;
    category: string;
    status: string;
  };
  sourceFailureCase: JsonRecord & { failureCaseId: string };
  agent: JsonRecord;
  scenario: JsonRecord;
  contract: JsonRecord;
  promotion: JsonRecord;
  collectionMembership: JsonRecord;
  focusedReruns: Array<JsonRecord & { agentProfile: string; regressionResult: string; runOutcome: string; runRef: JsonRecord }>;
  keyEvidenceRefs: JsonRecord[];
}

export interface RegressionExecutionResult {
  schemaVersion: string;
  artifactKind: string;
  result: {
    resultId: string;
    createdAt: string;
    regressionId: string;
    regressionVersion: string;
    agentProfile: string;
    agentVersion: string;
    regressionResult: string;
    runOutcome: string;
    runRef: JsonRecord;
    environmentId: string;
    oracle: JsonRecord;
    evidenceRefs: JsonRecord[];
    releaseEligibility: string;
  };
}

export interface RegressionCollection {
  schemaVersion: string;
  artifactKind: string;
  collection: JsonRecord & { collectionId: string; collectionVersion: string; category: string; status: string };
  members: Array<JsonRecord & { regressionId: string; regressionVersion: string; status: string; category: string; stableSignature: string }>;
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

const asOptionalObject = (value: unknown, label: string): JsonRecord | null => {
  if (value === null || value === undefined) return null;
  return asObject(value, label);
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
  const verification = asOptionalObject(artifact.verification, "verification");
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
    verification: verification ? {
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
    } : null,
    outcome: {
      status: asString(outcome.status, "outcome.status"),
      source: asString(outcome.source, "outcome.source"),
      agentQualityEligible: asBoolean(outcome.agent_quality_eligible, "outcome.agent_quality_eligible"),
      formalRunStarted: asBoolean(outcome.formal_run_started, "outcome.formal_run_started"),
      ...(typeof outcome.reason === "string" ? { reason: outcome.reason } : {}),
      ...(typeof outcome.attribution === "string" ? { attribution: outcome.attribution } : {}),
      ...(typeof outcome.agent_started === "boolean" ? { agentStarted: outcome.agent_started } : {}),
    },
    runtimeBudget: asObject(artifact.runtime_budget, "runtime_budget"),
    failureAttribution: asOptionalObject(artifact.failure_attribution, "failure_attribution"),
    healthContext: asOptionalObject(artifact.health_context, "health_context"),
  };
};

const normalizeFailureCase = (raw: unknown): FailureCase => {
  const artifact = asObject(raw, "failure case artifact");
  const metadata = asObject(artifact.failure_case, "failure_case");
  const sourceRun = asObject(artifact.source_run, "source_run");
  const signature = asObject(artifact.failure_signature, "failure_signature");
  const reproductionAttempts = asArray(artifact.reproduction_attempts, "reproduction_attempts").map((attempt) => {
    const value = asObject(attempt, "reproduction attempt");
    return {
      ...value,
      runId: asString(value.run_id, "reproduction_attempt.run_id"),
      environmentId: asString(value.environment_id, "reproduction_attempt.environment_id"),
      status: asString(value.status, "reproduction_attempt.status"),
    } as FailureCase["reproductionAttempts"][number];
  });
  return {
    schemaVersion: asString(artifact.schema_version, "failure case schema_version"),
    artifactKind: asString(artifact.artifact_kind, "failure case artifact_kind"),
    failureCase: {
      failureCaseId: asString(metadata.failure_case_id, "failure_case.failure_case_id"),
      createdAt: asString(metadata.created_at, "failure_case.created_at"),
      updatedAt: asString(metadata.updated_at, "failure_case.updated_at"),
      workflowState: asString(metadata.workflow_state, "failure_case.workflow_state"),
      currentStatus: asString(metadata.current_status, "failure_case.current_status"),
      isRegression: asBoolean(metadata.is_regression, "failure_case.is_regression"),
      regressionStatus: asString(metadata.regression_status, "failure_case.regression_status"),
    },
    sourceRun: {
      ...sourceRun,
      runId: asString(sourceRun.run_id, "source_run.run_id"),
      environmentId: asString(sourceRun.environment_id, "source_run.environment_id"),
    },
    agent: asObject(artifact.agent, "failure case agent"),
    scenario: asObject(artifact.scenario, "failure case scenario"),
    classification: asObject(artifact.classification, "classification"),
    failureSignature: {
      signatureVersion: asString(signature.signature_version, "failure_signature.signature_version"),
      value: asString(signature.value, "failure_signature.value"),
      components: asObject(signature.components, "failure_signature.components"),
    },
    failureObservation: asObject(artifact.failure_observation, "failure_observation"),
    evidenceRefs: asArray(artifact.evidence_refs, "evidence_refs").map((ref) => asObject(ref, "evidence ref")),
    reproductionAttempts,
    validation: asOptionalObject(artifact.validation, "validation"),
    regression: asObject(artifact.regression, "regression"),
    promotion: asOptionalObject(artifact.promotion, "promotion"),
  };
};

export const reviewedRuns: RunEvidence[] = [
  normalizeArtifact(normalArtifact),
  normalizeArtifact(responseLostArtifact),
  normalizeArtifact(agentFailArtifact),
  normalizeArtifact(environmentErrorArtifact),
  normalizeArtifact(reproductionArtifact),
  normalizeArtifact(regressionStabilityOneArtifact),
  normalizeArtifact(regressionStabilityTwoArtifact),
  normalizeArtifact(regressionFixedCandidateArtifact),
];

export const historicalFailureCase: FailureCase = normalizeFailureCase(failureCaseArtifact);

export const reviewedFailureCases: FailureCase[] = [normalizeFailureCase(promotedFailureCaseArtifact)];

const normalizeRegression = (raw: unknown): Regression => {
  const artifact = asObject(raw, "regression artifact");
  const metadata = asObject(artifact.regression, "regression");
  const source = asObject(artifact.source_failure_case, "source_failure_case");
  const focusedReruns = asArray(artifact.focused_reruns, "focused_reruns").map((item) => {
    const value = asObject(item, "focused rerun");
    return {
      ...value,
      agentProfile: asString(value.agent_profile, "focused_rerun.agent_profile"),
      regressionResult: asString(value.regression_result, "focused_rerun.regression_result"),
      runOutcome: asString(value.run_outcome, "focused_rerun.run_outcome"),
      runRef: asObject(value.run_ref, "focused_rerun.run_ref"),
    } as Regression["focusedReruns"][number];
  });
  return {
    schemaVersion: asString(artifact.schema_version, "regression.schema_version"),
    artifactKind: asString(artifact.artifact_kind, "regression.artifact_kind"),
    regression: {
      regressionId: asString(metadata.regression_id, "regression.regression_id"),
      regressionVersion: asString(metadata.regression_version, "regression.regression_version"),
      createdAt: asString(metadata.created_at, "regression.created_at"),
      updatedAt: asString(metadata.updated_at, "regression.updated_at"),
      lifecycleStatus: asString(metadata.lifecycle_status, "regression.lifecycle_status"),
      category: asString(metadata.category, "regression.category"),
      status: asString(metadata.status, "regression.status"),
    },
    sourceFailureCase: {
      ...source,
      failureCaseId: asString(source.failure_case_id, "source_failure_case.failure_case_id"),
    },
    agent: asObject(artifact.agent, "regression.agent"),
    scenario: asObject(artifact.scenario, "regression.scenario"),
    contract: asObject(artifact.contract, "regression.contract"),
    promotion: asObject(artifact.promotion, "regression.promotion"),
    collectionMembership: asObject(artifact.collection_membership, "regression.collection_membership"),
    focusedReruns,
    keyEvidenceRefs: asArray(artifact.key_evidence_refs, "key_evidence_refs").map((value) => asObject(value, "key evidence ref")),
  };
};

const normalizeRegressionResult = (raw: unknown): RegressionExecutionResult => {
  const artifact = asObject(raw, "regression result artifact");
  const result = asObject(artifact.result, "regression result");
  return {
    schemaVersion: asString(artifact.schema_version, "regression result.schema_version"),
    artifactKind: asString(artifact.artifact_kind, "regression result.artifact_kind"),
    result: {
      resultId: asString(result.result_id, "result.result_id"),
      createdAt: asString(result.created_at, "result.created_at"),
      regressionId: asString(result.regression_id, "result.regression_id"),
      regressionVersion: asString(result.regression_version, "result.regression_version"),
      agentProfile: asString(result.agent_profile, "result.agent_profile"),
      agentVersion: asString(result.agent_version, "result.agent_version"),
      regressionResult: asString(result.regression_result, "result.regression_result"),
      runOutcome: asString(result.run_outcome, "result.run_outcome"),
      runRef: asObject(result.run_ref, "result.run_ref"),
      environmentId: asString(result.environment_id, "result.environment_id"),
      oracle: asObject(result.oracle, "result.oracle"),
      evidenceRefs: asArray(result.evidence_refs, "result.evidence_refs").map((value) => asObject(value, "result evidence ref")),
      releaseEligibility: asString(result.release_eligibility, "result.release_eligibility"),
    },
  };
};

const normalizeRegressionCollection = (raw: unknown): RegressionCollection => {
  const artifact = asObject(raw, "regression collection artifact");
  const collection = asObject(artifact.collection, "collection");
  const members = asArray(artifact.members, "collection.members").map((item) => {
    const value = asObject(item, "collection member");
    return {
      ...value,
      regressionId: asString(value.regression_id, "collection member.regression_id"),
      regressionVersion: asString(value.regression_version, "collection member.regression_version"),
      status: asString(value.status, "collection member.status"),
      category: asString(value.category, "collection member.category"),
      stableSignature: asString(value.stable_signature, "collection member.stable_signature"),
    } as RegressionCollection["members"][number];
  });
  return {
    schemaVersion: asString(artifact.schema_version, "collection.schema_version"),
    artifactKind: asString(artifact.artifact_kind, "collection.artifact_kind"),
    collection: {
      ...collection,
      collectionId: asString(collection.collection_id, "collection.collection_id"),
      collectionVersion: asString(collection.collection_version, "collection.collection_version"),
      category: asString(collection.category, "collection.category"),
      status: asString(collection.status, "collection.status"),
    },
    members,
  };
};

export const reviewedRegressions: Regression[] = [normalizeRegression(regressionArtifact)];
export const reviewedRegressionResults: RegressionExecutionResult[] = [
  normalizeRegressionResult(regressionKnownBadResultArtifact),
  normalizeRegressionResult(regressionFixedCandidateResultArtifact),
];
export const reviewedRegressionCollection: RegressionCollection = normalizeRegressionCollection(regressionCollectionArtifact);

export const getRun = (runId: string): RunEvidence | undefined => reviewedRuns.find((run) => run.run.runId === runId);

export const isFaultedRun = (run: RunEvidence): boolean => run.fault.planned && run.fault.triggered;

export const isAgentFailureRun = (run: RunEvidence): boolean => run.outcome.status === "FAIL" && run.outcome.attribution === "Agent";

export const isEnvironmentErrorRun = (run: RunEvidence): boolean => run.outcome.status === "ERROR" && run.outcome.attribution === "Platform/Environment";

export const getFailureCase = (failureCaseId: string): FailureCase | undefined => reviewedFailureCases.find((item) => item.failureCase.failureCaseId === failureCaseId);

export const getFailureCaseForRun = (runId: string): FailureCase | undefined => reviewedFailureCases.find((item) => item.sourceRun.runId === runId || item.reproductionAttempts.some((attempt) => attempt.runId === runId));

export const getRegression = (regressionId: string): Regression | undefined => reviewedRegressions.find((item) => item.regression.regressionId === regressionId);

export const getRegressionResult = (resultId: string): RegressionExecutionResult | undefined => reviewedRegressionResults.find((item) => item.result.resultId === resultId);

export const getRegressionResults = (regressionId: string): RegressionExecutionResult[] => reviewedRegressionResults.filter((item) => item.result.regressionId === regressionId);

export const getRegressionResultForRun = (runId: string): RegressionExecutionResult | undefined => reviewedRegressionResults.find((item) => item.result.runRef.run_id === runId);

export const getRegressionForRun = (runId: string): Regression | undefined => {
  const result = getRegressionResultForRun(runId);
  return result ? getRegression(result.result.regressionId) : undefined;
};

export const getUsage = (run: RunEvidence): JsonRecord => asOptionalObject(run.llmProvider.raw_usage, "llm_provider.raw_usage") || {};

export const getDerivedCost = (run: RunEvidence): JsonRecord => asOptionalObject(run.llmProvider.derived_cost, "llm_provider.derived_cost") || {};
