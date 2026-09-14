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
import evaluationSuiteArtifact from "../../../runtime/reviewed-evaluation-suite.json";
import evaluationBaselineArtifact from "../../../runtime/reviewed-evaluation-baseline.json";
import evaluationCandidateArtifact from "../../../runtime/reviewed-evaluation-candidate.json";
import evaluationComparisonArtifact from "../../../runtime/reviewed-evaluation-comparison.json";
import evaluationBaselineNormalRunArtifact from "../../../runtime/reviewed-evaluation-baseline-normal-run.json";
import evaluationBaselineRecoveryRunArtifact from "../../../runtime/reviewed-evaluation-baseline-recovery-run.json";
import evaluationBaselineRegressionRunArtifact from "../../../runtime/reviewed-evaluation-baseline-regression-run.json";
import evaluationCandidateNormalRunArtifact from "../../../runtime/reviewed-evaluation-candidate-normal-run.json";
import evaluationCandidateRecoveryRunArtifact from "../../../runtime/reviewed-evaluation-candidate-recovery-run.json";
import evaluationCandidateRegressionRunArtifact from "../../../runtime/reviewed-evaluation-candidate-regression-run.json";
import evaluationBaselineRegressionResultArtifact from "../../../runtime/reviewed-evaluation-baseline-regression-result.json";
import evaluationCandidateRegressionResultArtifact from "../../../runtime/reviewed-evaluation-candidate-regression-result.json";
import qualityPolicyArtifact from "../../../runtime/reviewed-quality-policy.json";
import qualityGateBaselineArtifact from "../../../runtime/reviewed-quality-gate-baseline.json";
import qualityGateCandidateArtifact from "../../../runtime/reviewed-quality-gate-candidate.json";
import releaseDecisionBaselineArtifact from "../../../runtime/reviewed-release-decision-baseline.json";
import releaseDecisionCandidateArtifact from "../../../runtime/reviewed-release-decision-candidate.json";
import incidentSourceFailureRunArtifact from "../../../runtime/reviewed-rpf16-incident-source-failure-run.json";
import incidentFailureReproductionRunArtifact from "../../../runtime/reviewed-rpf16-incident-failure-reproduction-run.json";
import incidentStabilityOneRunArtifact from "../../../runtime/reviewed-rpf16-incident-stability-01-run.json";
import incidentStabilityTwoRunArtifact from "../../../runtime/reviewed-rpf16-incident-stability-02-run.json";
import incidentFixedFocusRunArtifact from "../../../runtime/reviewed-rpf16-incident-fixed-focus-run.json";
import incidentFailureCaseArtifact from "../../../runtime/reviewed-rpf16-incident-failure-case.json";
import incidentRegressionArtifact from "../../../runtime/reviewed-rpf16-incident-regression.json";
import incidentRegressionCollectionArtifact from "../../../runtime/reviewed-rpf16-incident-regression-collection.json";
import incidentKnownBadResultArtifact from "../../../runtime/reviewed-rpf16-incident-known-bad-regression-result.json";
import incidentFixedResultArtifact from "../../../runtime/reviewed-rpf16-incident-fixed-regression-result.json";
import incidentEvaluationSuiteArtifact from "../../../runtime/reviewed-rpf16-incident-suite.json";
import incidentBaselineEvaluationArtifact from "../../../runtime/reviewed-rpf16-incident-baseline-evaluation.json";
import incidentCandidateEvaluationArtifact from "../../../runtime/reviewed-rpf16-incident-candidate-evaluation.json";
import incidentComparisonArtifact from "../../../runtime/reviewed-rpf16-incident-comparison.json";
import incidentQualityPolicyArtifact from "../../../runtime/reviewed-rpf16-incident-quality-policy.json";
import incidentBaselineGateArtifact from "../../../runtime/reviewed-rpf16-incident-baseline-gate.json";
import incidentCandidateGateArtifact from "../../../runtime/reviewed-rpf16-incident-candidate-gate.json";
import incidentBaselineDecisionArtifact from "../../../runtime/reviewed-rpf16-incident-baseline-decision.json";
import incidentCandidateDecisionArtifact from "../../../runtime/reviewed-rpf16-incident-candidate-decision.json";
import incidentBaselineLocalRunArtifact from "../../../runtime/reviewed-rpf16-incident-evaluation-baseline-local-run.json";
import incidentBaselineRecoveryRunArtifact from "../../../runtime/reviewed-rpf16-incident-evaluation-baseline-response-lost-run.json";
import incidentBaselineRegressionRunArtifact from "../../../runtime/reviewed-rpf16-incident-evaluation-baseline-external-regression-run.json";
import incidentCandidateLocalRunArtifact from "../../../runtime/reviewed-rpf16-incident-evaluation-candidate-local-run.json";
import incidentCandidateRecoveryRunArtifact from "../../../runtime/reviewed-rpf16-incident-evaluation-candidate-response-lost-run.json";
import incidentCandidateRegressionRunArtifact from "../../../runtime/reviewed-rpf16-incident-evaluation-candidate-external-regression-run.json";
import incidentBaselineEvaluationRegressionResultArtifact from "../../../runtime/reviewed-rpf16-incident-baseline-evaluation-regression-result.json";
import incidentCandidateEvaluationRegressionResultArtifact from "../../../runtime/reviewed-rpf16-incident-candidate-evaluation-regression-result.json";

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

export interface EvaluationSuiteMember {
  memberId: string;
  stableRef: JsonRecord;
  category: string;
  required: boolean;
  description: string;
  scenarioRef: JsonRecord;
  regressionRef: JsonRecord | null;
  execution: JsonRecord;
  expectedEvidence: JsonRecord;
}

export interface EvaluationSuite {
  schemaVersion: string;
  artifactKind: string;
  suite: {
    suiteId: string;
    suiteVersion: string;
    suiteIdentity: string;
    name: string;
    purpose: string;
    agentDomain: string;
    members: EvaluationSuiteMember[];
    memberContractDigest: string;
    executionPolicy: JsonRecord;
    sourceIdentity: JsonRecord;
  };
}

export interface EvaluationMemberResult {
  memberId: string;
  category: string;
  required: boolean;
  scenarioRef: JsonRecord;
  regressionRef: JsonRecord | null;
  oracleId: string;
  runRef: JsonRecord;
  environmentId: string | null;
  runOutcome: string;
  itemResult: string;
  attribution: string;
  validQualityEvidence: boolean;
  validEvidenceStatus: string;
  evidenceGapReasons: string[];
  durationMs: number | null;
  usage: JsonRecord;
  fault: JsonRecord;
  recoveryStatus: string | null;
  evidenceRefs: JsonRecord[];
  regressionResultRef?: JsonRecord;
  regressionResult?: string;
}

export interface EvaluationResult {
  schemaVersion: string;
  artifactKind: string;
  evaluation: {
    evaluationId: string;
    evaluationStatus: string;
    startedAt: string;
    endedAt: string;
    durationMs: number | null;
    suiteRef: JsonRecord;
    suiteMemberIds: string[];
    agent: JsonRecord;
    memberResults: EvaluationMemberResult[];
    outcomeCounts: Record<string, number>;
    runOutcomeCounts: Record<string, number>;
    summary: JsonRecord;
    incompleteOrUnknown: JsonRecord[];
    nonReleaseBoundary: string;
    runtime: JsonRecord;
  };
}

export interface ComparisonSide {
  itemResult: string;
  runOutcome: string;
  attribution: string;
  validEvidenceStatus: string;
  runRef: JsonRecord;
  resultRef: JsonRecord | null;
  evidenceGapReasons: string[];
}

export interface EvaluationComparisonMember {
  memberId: string;
  category: string;
  required: boolean;
  scenarioRef: JsonRecord;
  regressionRef: JsonRecord | null;
  baseline: ComparisonSide;
  candidate: ComparisonSide;
  classification: string;
  reasons: string[];
}

export interface EvaluationComparison {
  schemaVersion: string;
  artifactKind: string;
  comparison: {
    comparisonId: string;
    status: string;
    suiteRef: JsonRecord | null;
    baseline: JsonRecord;
    candidate: JsonRecord;
    perMemberComparison: EvaluationComparisonMember[];
    aggregate: JsonRecord | null;
    validationErrors: string[];
    nonReleaseBoundary: string;
    runtime: JsonRecord;
  };
}

export interface QualityPolicy {
  schemaVersion: string;
  artifactKind: string;
  policy: {
    policyId: string;
    policyVersion: string;
    policyIdentity: string;
    name: string;
    purpose: string;
    compatibleSuite: JsonRecord;
    requiredEvidence: JsonRecord;
    rules: JsonRecord[];
    decisionPrecedence: string[];
    unknownValueSemantics: JsonRecord;
    sourceIdentity: JsonRecord;
  };
}

export interface QualityGateEvaluation {
  schemaVersion: string;
  artifactKind: string;
  gateEvaluation: {
    gateEvaluationId: string;
    evaluatedAt: string;
    status: string;
    decisionSubject: string;
    policyRef: JsonRecord | null;
    suiteRef: JsonRecord | null;
    agentUnderEvaluation: JsonRecord;
    candidateAgent: JsonRecord | null;
    baselineAgent: JsonRecord | null;
    subjectEvaluationRef: JsonRecord | null;
    candidateEvaluationRef: JsonRecord | null;
    baselineEvaluationRef: JsonRecord | null;
    comparisonRef: JsonRecord | null;
    regressionRef: JsonRecord | null;
    decisionStatus: string | null;
    ruleResults: JsonRecord[];
    blockingReasons: JsonRecord[];
    evidenceGapReasons: JsonRecord[];
    reviewReasons: JsonRecord[];
    softWarnings: JsonRecord[];
    coverageFacts: JsonRecord;
    regressionFacts: JsonRecord;
    recoveryFacts: JsonRecord;
    validationErrors: string[];
    authorizationBoundary: JsonRecord;
    sourceIdentity: JsonRecord;
  };
}

export interface ReleaseDecision {
  schemaVersion: string;
  artifactKind: string;
  releaseDecision: {
    releaseDecisionId: string;
    decisionTimestamp: string;
    decisionStatus: string;
    decisionSubject: string;
    evaluatedAgent: JsonRecord;
    evaluatedAgentVersion: string;
    candidateAgent: JsonRecord | null;
    candidateAgentVersion: string | null;
    baselineAgent: JsonRecord | null;
    baselineAgentVersion: string | null;
    policyRef: JsonRecord;
    suiteRef: JsonRecord;
    candidateEvaluationRef: JsonRecord;
    baselineEvaluationRef: JsonRecord | null;
    comparisonRef: JsonRecord;
    gateEvaluationRef: JsonRecord;
    regressionRef: JsonRecord;
    blockingReasons: JsonRecord[];
    reviewReasons: JsonRecord[];
    softWarnings: JsonRecord[];
    evidenceGapReasons: JsonRecord[];
    validEvidenceCoverage: JsonRecord;
    historicalRegression: JsonRecord;
    recoveryFault: JsonRecord;
    evidenceRefs: JsonRecord[];
    authorizationBoundary: JsonRecord;
    history: JsonRecord;
    sourceIdentity: JsonRecord;
  };
}

export interface AgentSummary {
  agentId: string;
  domain: string;
  agentType: string;
  contractId: string;
  versions: string[];
  profiles: string[];
  scenarioRefs: JsonRecord[];
  runIds: string[];
  failureCaseIds: string[];
  regressionIds: string[];
  evaluationIds: string[];
  decisionIds: string[];
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

const asOptionalNumber = (value: unknown, label: string): number | null => {
  if (value === null || value === undefined) return null;
  return asNumber(value, label);
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

export let reviewedRuns: RunEvidence[] = [
  normalizeArtifact(normalArtifact),
  normalizeArtifact(responseLostArtifact),
  normalizeArtifact(agentFailArtifact),
  normalizeArtifact(environmentErrorArtifact),
  normalizeArtifact(reproductionArtifact),
  normalizeArtifact(regressionStabilityOneArtifact),
  normalizeArtifact(regressionStabilityTwoArtifact),
  normalizeArtifact(regressionFixedCandidateArtifact),
  normalizeArtifact(incidentSourceFailureRunArtifact),
  normalizeArtifact(incidentFailureReproductionRunArtifact),
  normalizeArtifact(incidentStabilityOneRunArtifact),
  normalizeArtifact(incidentStabilityTwoRunArtifact),
  normalizeArtifact(incidentFixedFocusRunArtifact),
];

export const historicalFailureCase: FailureCase = normalizeFailureCase(failureCaseArtifact);

export let reviewedFailureCases: FailureCase[] = [normalizeFailureCase(promotedFailureCaseArtifact), normalizeFailureCase(incidentFailureCaseArtifact)];

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

const normalizeEvaluationSuite = (raw: unknown): EvaluationSuite => {
  const artifact = asObject(raw, "evaluation suite artifact");
  const suite = asObject(artifact.suite, "evaluation suite");
  const members = asArray(suite.members, "evaluation suite.members").map((rawMember) => {
    const member = asObject(rawMember, "evaluation suite member");
    return {
      memberId: asString(member.member_id, "evaluation member_id"),
      stableRef: asObject(member.stable_ref, "evaluation member stable_ref"),
      category: asString(member.category, "evaluation member category"),
      required: asBoolean(member.required, "evaluation member required"),
      description: asString(member.description, "evaluation member description"),
      scenarioRef: asObject(member.scenario_ref, "evaluation member scenario_ref"),
      regressionRef: asOptionalObject(member.regression_ref, "evaluation member regression_ref"),
      execution: asObject(member.execution, "evaluation member execution"),
      expectedEvidence: asObject(member.expected_evidence, "evaluation member expected_evidence"),
    };
  });
  return {
    schemaVersion: asString(artifact.schema_version, "evaluation suite schema_version"),
    artifactKind: asString(artifact.artifact_kind, "evaluation suite artifact_kind"),
    suite: {
      suiteId: asString(suite.suite_id, "suite.suite_id"),
      suiteVersion: asString(suite.suite_version, "suite.suite_version"),
      suiteIdentity: asString(suite.suite_identity, "suite.suite_identity"),
      name: asString(suite.name, "suite.name"),
      purpose: asString(suite.purpose, "suite.purpose"),
      agentDomain: asString(suite.agent_domain, "suite.agent_domain"),
      members,
      memberContractDigest: asString(suite.member_contract_digest, "suite.member_contract_digest"),
      executionPolicy: asObject(suite.execution_policy, "suite.execution_policy"),
      sourceIdentity: asObject(suite.source_identity, "suite.source_identity"),
    },
  };
};

const normalizeEvaluationMember = (raw: unknown): EvaluationMemberResult => {
  const item = asObject(raw, "evaluation member result");
  return {
    memberId: asString(item.member_id, "evaluation item.member_id"),
    category: asString(item.category, "evaluation item.category"),
    required: asBoolean(item.required, "evaluation item.required"),
    scenarioRef: asObject(item.scenario_ref, "evaluation item.scenario_ref"),
    regressionRef: asOptionalObject(item.regression_ref, "evaluation item.regression_ref"),
    oracleId: asString(item.oracle_id, "evaluation item.oracle_id"),
    runRef: asObject(item.run_ref, "evaluation item.run_ref"),
    environmentId: typeof item.environment_id === "string" ? item.environment_id : null,
    runOutcome: asString(item.run_outcome, "evaluation item.run_outcome"),
    itemResult: asString(item.item_result, "evaluation item.item_result"),
    attribution: asString(item.attribution, "evaluation item.attribution"),
    validQualityEvidence: asBoolean(item.valid_quality_evidence, "evaluation item.valid_quality_evidence"),
    validEvidenceStatus: asString(item.valid_evidence_status, "evaluation item.valid_evidence_status"),
    evidenceGapReasons: asArray(item.evidence_gap_reasons, "evaluation item.evidence_gap_reasons").map((value) => asString(value, "evaluation gap reason")),
    durationMs: asOptionalNumber(item.duration_ms, "evaluation item.duration_ms"),
    usage: asObject(item.usage, "evaluation item.usage"),
    fault: asObject(item.fault, "evaluation item.fault"),
    recoveryStatus: typeof item.recovery_status === "string" ? item.recovery_status : null,
    evidenceRefs: asArray(item.evidence_refs, "evaluation item.evidence_refs").map((value) => asObject(value, "evaluation item evidence ref")),
    ...(item.regression_result_ref ? { regressionResultRef: asObject(item.regression_result_ref, "evaluation item.regression_result_ref") } : {}),
    ...(typeof item.regression_result === "string" ? { regressionResult: item.regression_result } : {}),
  };
};

const normalizeEvaluation = (raw: unknown): EvaluationResult => {
  const artifact = asObject(raw, "evaluation result artifact");
  const evaluation = asObject(artifact.evaluation, "evaluation result");
  return {
    schemaVersion: asString(artifact.schema_version, "evaluation result schema_version"),
    artifactKind: asString(artifact.artifact_kind, "evaluation result artifact_kind"),
    evaluation: {
      evaluationId: asString(evaluation.evaluation_id, "evaluation.evaluation_id"),
      evaluationStatus: asString(evaluation.evaluation_status, "evaluation.evaluation_status"),
      startedAt: asString(evaluation.started_at, "evaluation.started_at"),
      endedAt: asString(evaluation.ended_at, "evaluation.ended_at"),
      durationMs: asOptionalNumber(evaluation.duration_ms, "evaluation.duration_ms"),
      suiteRef: asObject(evaluation.suite_ref, "evaluation.suite_ref"),
      suiteMemberIds: asArray(evaluation.suite_member_ids, "evaluation.suite_member_ids").map((value) => asString(value, "evaluation suite member id")),
      agent: asObject(evaluation.agent, "evaluation.agent"),
      memberResults: asArray(evaluation.member_results, "evaluation.member_results").map(normalizeEvaluationMember),
      outcomeCounts: asObject(evaluation.outcome_counts, "evaluation.outcome_counts") as Record<string, number>,
      runOutcomeCounts: asObject(evaluation.run_outcome_counts, "evaluation.run_outcome_counts") as Record<string, number>,
      summary: asObject(evaluation.summary, "evaluation.summary"),
      incompleteOrUnknown: asArray(evaluation.incomplete_or_unknown, "evaluation.incomplete_or_unknown").map((value) => asObject(value, "evaluation incomplete item")),
      nonReleaseBoundary: asString(evaluation.non_release_boundary, "evaluation.non_release_boundary"),
      runtime: asObject(evaluation.runtime, "evaluation.runtime"),
    },
  };
};

const normalizeComparisonSide = (raw: unknown): ComparisonSide => {
  const side = asObject(raw, "comparison side");
  return {
    itemResult: asString(side.item_result, "comparison side.item_result"),
    runOutcome: asString(side.run_outcome, "comparison side.run_outcome"),
    attribution: asString(side.attribution, "comparison side.attribution"),
    validEvidenceStatus: asString(side.valid_evidence_status, "comparison side.valid_evidence_status"),
    runRef: asObject(side.run_ref, "comparison side.run_ref"),
    resultRef: asOptionalObject(side.result_ref, "comparison side.result_ref"),
    evidenceGapReasons: asArray(side.evidence_gap_reasons, "comparison side.evidence_gap_reasons").map((value) => asString(value, "comparison gap reason")),
  };
};

const normalizeComparisonMember = (raw: unknown): EvaluationComparisonMember => {
  const item = asObject(raw, "comparison member");
  return {
    memberId: asString(item.member_id, "comparison member.member_id"),
    category: asString(item.category, "comparison member.category"),
    required: asBoolean(item.required, "comparison member.required"),
    scenarioRef: asObject(item.scenario_ref, "comparison member.scenario_ref"),
    regressionRef: asOptionalObject(item.regression_ref, "comparison member.regression_ref"),
    baseline: normalizeComparisonSide(item.baseline),
    candidate: normalizeComparisonSide(item.candidate),
    classification: asString(item.classification, "comparison member.classification"),
    reasons: asArray(item.reasons, "comparison member.reasons").map((value) => asString(value, "comparison member reason")),
  };
};

const normalizeComparison = (raw: unknown): EvaluationComparison => {
  const artifact = asObject(raw, "evaluation comparison artifact");
  const comparison = asObject(artifact.comparison, "evaluation comparison");
  return {
    schemaVersion: asString(artifact.schema_version, "evaluation comparison schema_version"),
    artifactKind: asString(artifact.artifact_kind, "evaluation comparison artifact_kind"),
    comparison: {
      comparisonId: asString(comparison.comparison_id, "comparison.comparison_id"),
      status: asString(comparison.status, "comparison.status"),
      suiteRef: asOptionalObject(comparison.suite_ref, "comparison.suite_ref"),
      baseline: asObject(comparison.baseline, "comparison.baseline"),
      candidate: asObject(comparison.candidate, "comparison.candidate"),
      perMemberComparison: asArray(comparison.per_member_comparison, "comparison.per_member_comparison").map(normalizeComparisonMember),
      aggregate: asOptionalObject(comparison.aggregate, "comparison.aggregate"),
      validationErrors: asArray(comparison.validation_errors, "comparison.validation_errors").map((value) => asString(value, "comparison validation error")),
      nonReleaseBoundary: asString(comparison.non_release_boundary, "comparison.non_release_boundary"),
      runtime: asObject(comparison.runtime, "comparison.runtime"),
    },
  };
};

const normalizeQualityPolicy = (raw: unknown): QualityPolicy => {
  const artifact = asObject(raw, "quality policy artifact");
  const policy = asObject(artifact.policy, "quality policy");
  return {
    schemaVersion: asString(artifact.schema_version, "quality policy schema_version"),
    artifactKind: asString(artifact.artifact_kind, "quality policy artifact_kind"),
    policy: {
      policyId: asString(policy.policy_id, "policy.policy_id"),
      policyVersion: asString(policy.policy_version, "policy.policy_version"),
      policyIdentity: asString(policy.policy_identity, "policy.policy_identity"),
      name: asString(policy.name, "policy.name"),
      purpose: asString(policy.purpose, "policy.purpose"),
      compatibleSuite: asObject(policy.compatible_suite, "policy.compatible_suite"),
      requiredEvidence: asObject(policy.required_evidence, "policy.required_evidence"),
      rules: asArray(policy.rules, "policy.rules").map((value) => asObject(value, "policy rule")),
      decisionPrecedence: asArray(policy.decision_precedence, "policy.decision_precedence").map((value) => asString(value, "policy precedence")),
      unknownValueSemantics: asObject(policy.unknown_value_semantics, "policy.unknown_value_semantics"),
      sourceIdentity: asObject(policy.source_identity, "policy.source_identity"),
    },
  };
};

const normalizeQualityGate = (raw: unknown): QualityGateEvaluation => {
  const artifact = asObject(raw, "quality gate artifact");
  const gate = asObject(artifact.gate_evaluation, "quality gate evaluation");
  const optionalObject = (value: unknown, label: string): JsonRecord | null => value === null || value === undefined ? null : asObject(value, label);
  return {
    schemaVersion: asString(artifact.schema_version, "quality gate schema_version"),
    artifactKind: asString(artifact.artifact_kind, "quality gate artifact_kind"),
    gateEvaluation: {
      gateEvaluationId: asString(gate.gate_evaluation_id, "gate.gate_evaluation_id"),
      evaluatedAt: asString(gate.evaluated_at, "gate.evaluated_at"),
      status: asString(gate.status, "gate.status"),
      decisionSubject: asString(gate.decision_subject, "gate.decision_subject"),
      policyRef: optionalObject(gate.policy_ref, "gate.policy_ref"),
      suiteRef: optionalObject(gate.suite_ref, "gate.suite_ref"),
      agentUnderEvaluation: asObject(gate.agent_under_evaluation, "gate.agent_under_evaluation"),
      candidateAgent: optionalObject(gate.candidate_agent, "gate.candidate_agent"),
      baselineAgent: optionalObject(gate.baseline_agent, "gate.baseline_agent"),
      subjectEvaluationRef: optionalObject(gate.subject_evaluation_ref, "gate.subject_evaluation_ref"),
      candidateEvaluationRef: optionalObject(gate.candidate_evaluation_ref, "gate.candidate_evaluation_ref"),
      baselineEvaluationRef: optionalObject(gate.baseline_evaluation_ref, "gate.baseline_evaluation_ref"),
      comparisonRef: optionalObject(gate.comparison_ref, "gate.comparison_ref"),
      regressionRef: optionalObject(gate.regression_ref, "gate.regression_ref"),
      decisionStatus: typeof gate.decision_status === "string" ? gate.decision_status : null,
      ruleResults: asArray(gate.rule_results, "gate.rule_results").map((value) => asObject(value, "gate rule result")),
      blockingReasons: asArray(gate.blocking_reasons, "gate.blocking_reasons").map((value) => asObject(value, "gate blocking reason")),
      evidenceGapReasons: asArray(gate.evidence_gap_reasons, "gate.evidence_gap_reasons").map((value) => asObject(value, "gate evidence gap")),
      reviewReasons: asArray(gate.review_reasons, "gate.review_reasons").map((value) => asObject(value, "gate review reason")),
      softWarnings: asArray(gate.soft_warnings, "gate.soft_warnings").map((value) => asObject(value, "gate soft warning")),
      coverageFacts: asObject(gate.coverage_facts, "gate.coverage_facts"),
      regressionFacts: asObject(gate.regression_facts, "gate.regression_facts"),
      recoveryFacts: asObject(gate.recovery_facts, "gate.recovery_facts"),
      validationErrors: asArray(gate.validation_errors, "gate.validation_errors").map((value) => asString(value, "gate validation error")),
      authorizationBoundary: asObject(gate.authorization_boundary, "gate.authorization_boundary"),
      sourceIdentity: asObject(gate.source_identity, "gate.source_identity"),
    },
  };
};

const normalizeReleaseDecision = (raw: unknown): ReleaseDecision => {
  const artifact = asObject(raw, "release decision artifact");
  const decision = asObject(artifact.release_decision, "release decision");
  const optionalObject = (value: unknown, label: string): JsonRecord | null => value === null || value === undefined ? null : asObject(value, label);
  return {
    schemaVersion: asString(artifact.schema_version, "release decision schema_version"),
    artifactKind: asString(artifact.artifact_kind, "release decision artifact_kind"),
    releaseDecision: {
      releaseDecisionId: asString(decision.release_decision_id, "decision.release_decision_id"),
      decisionTimestamp: asString(decision.decision_timestamp, "decision.decision_timestamp"),
      decisionStatus: asString(decision.decision_status, "decision.decision_status"),
      decisionSubject: asString(decision.decision_subject, "decision.decision_subject"),
      evaluatedAgent: asObject(decision.evaluated_agent, "decision.evaluated_agent"),
      evaluatedAgentVersion: asString(decision.evaluated_agent_version, "decision.evaluated_agent_version"),
      candidateAgent: optionalObject(decision.candidate_agent, "decision.candidate_agent"),
      candidateAgentVersion: typeof decision.candidate_agent_version === "string" ? decision.candidate_agent_version : null,
      baselineAgent: optionalObject(decision.baseline_agent, "decision.baseline_agent"),
      baselineAgentVersion: typeof decision.baseline_agent_version === "string" ? decision.baseline_agent_version : null,
      policyRef: asObject(decision.policy_ref, "decision.policy_ref"),
      suiteRef: asObject(decision.suite_ref, "decision.suite_ref"),
      candidateEvaluationRef: asObject(decision.candidate_evaluation_ref, "decision.candidate_evaluation_ref"),
      baselineEvaluationRef: optionalObject(decision.baseline_evaluation_ref, "decision.baseline_evaluation_ref"),
      comparisonRef: asObject(decision.comparison_ref, "decision.comparison_ref"),
      gateEvaluationRef: asObject(decision.gate_evaluation_ref, "decision.gate_evaluation_ref"),
      regressionRef: asObject(decision.regression_ref, "decision.regression_ref"),
      blockingReasons: asArray(decision.blocking_reasons, "decision.blocking_reasons").map((value) => asObject(value, "decision blocking reason")),
      reviewReasons: asArray(decision.review_reasons, "decision.review_reasons").map((value) => asObject(value, "decision review reason")),
      softWarnings: asArray(decision.soft_warnings, "decision.soft_warnings").map((value) => asObject(value, "decision soft warning")),
      evidenceGapReasons: asArray(decision.evidence_gap_reasons, "decision.evidence_gap_reasons").map((value) => asObject(value, "decision evidence gap")),
      validEvidenceCoverage: asObject(decision.valid_evidence_coverage, "decision.valid_evidence_coverage"),
      historicalRegression: asObject(decision.historical_regression, "decision.historical_regression"),
      recoveryFault: asObject(decision.recovery_fault, "decision.recovery_fault"),
      evidenceRefs: asArray(decision.evidence_refs, "decision.evidence_refs").map((value) => asObject(value, "decision evidence ref")),
      authorizationBoundary: asObject(decision.authorization_boundary, "decision.authorization_boundary"),
      history: asObject(decision.history, "decision.history"),
      sourceIdentity: asObject(decision.source_identity, "decision.source_identity"),
    },
  };
};

export let reviewedRegressions: Regression[] = [normalizeRegression(regressionArtifact), normalizeRegression(incidentRegressionArtifact)];
export let reviewedRegressionResults: RegressionExecutionResult[] = [
  normalizeRegressionResult(regressionKnownBadResultArtifact),
  normalizeRegressionResult(regressionFixedCandidateResultArtifact),
  normalizeRegressionResult(incidentKnownBadResultArtifact),
  normalizeRegressionResult(incidentFixedResultArtifact),
];
export let reviewedRegressionCollection: RegressionCollection = normalizeRegressionCollection(regressionCollectionArtifact);
export let reviewedRegressionCollections: RegressionCollection[] = [
  reviewedRegressionCollection,
  normalizeRegressionCollection(incidentRegressionCollectionArtifact),
];

export let reviewedEvaluationSuite: EvaluationSuite = normalizeEvaluationSuite(evaluationSuiteArtifact);
export let reviewedEvaluationSuites: EvaluationSuite[] = [
  reviewedEvaluationSuite,
  normalizeEvaluationSuite(incidentEvaluationSuiteArtifact),
];
export let reviewedEvaluations: EvaluationResult[] = [
  normalizeEvaluation(evaluationBaselineArtifact),
  normalizeEvaluation(evaluationCandidateArtifact),
  normalizeEvaluation(incidentBaselineEvaluationArtifact),
  normalizeEvaluation(incidentCandidateEvaluationArtifact),
];
export let reviewedEvaluationComparison: EvaluationComparison = normalizeComparison(evaluationComparisonArtifact);
export let reviewedEvaluationComparisons: EvaluationComparison[] = [
  reviewedEvaluationComparison,
  normalizeComparison(incidentComparisonArtifact),
];
export let reviewedQualityPolicy: QualityPolicy = normalizeQualityPolicy(qualityPolicyArtifact);
export let reviewedQualityPolicies: QualityPolicy[] = [
  reviewedQualityPolicy,
  normalizeQualityPolicy(incidentQualityPolicyArtifact),
];
export let reviewedQualityGates: QualityGateEvaluation[] = [
  normalizeQualityGate(qualityGateBaselineArtifact),
  normalizeQualityGate(qualityGateCandidateArtifact),
  normalizeQualityGate(incidentBaselineGateArtifact),
  normalizeQualityGate(incidentCandidateGateArtifact),
];
export let reviewedReleaseDecisions: ReleaseDecision[] = [
  normalizeReleaseDecision(releaseDecisionBaselineArtifact),
  normalizeReleaseDecision(releaseDecisionCandidateArtifact),
  normalizeReleaseDecision(incidentBaselineDecisionArtifact),
  normalizeReleaseDecision(incidentCandidateDecisionArtifact),
];
export let reviewedEvaluationRuns: RunEvidence[] = [
  normalizeArtifact(evaluationBaselineNormalRunArtifact),
  normalizeArtifact(evaluationBaselineRecoveryRunArtifact),
  normalizeArtifact(evaluationBaselineRegressionRunArtifact),
  normalizeArtifact(evaluationCandidateNormalRunArtifact),
  normalizeArtifact(evaluationCandidateRecoveryRunArtifact),
  normalizeArtifact(evaluationCandidateRegressionRunArtifact),
  normalizeArtifact(incidentBaselineLocalRunArtifact),
  normalizeArtifact(incidentBaselineRecoveryRunArtifact),
  normalizeArtifact(incidentBaselineRegressionRunArtifact),
  normalizeArtifact(incidentCandidateLocalRunArtifact),
  normalizeArtifact(incidentCandidateRecoveryRunArtifact),
  normalizeArtifact(incidentCandidateRegressionRunArtifact),
];
export let reviewedEvaluationRegressionResults: RegressionExecutionResult[] = [
  normalizeRegressionResult(evaluationBaselineRegressionResultArtifact),
  normalizeRegressionResult(evaluationCandidateRegressionResultArtifact),
  normalizeRegressionResult(incidentBaselineEvaluationRegressionResultArtifact),
  normalizeRegressionResult(incidentCandidateEvaluationRegressionResultArtifact),
];

let allReviewedRuns = [...reviewedRuns, ...reviewedEvaluationRuns];
let allRegressionResults = [...reviewedRegressionResults, ...reviewedEvaluationRegressionResults];

const agentText = (value: unknown, ...keys: string[]): string | null => {
  const record = value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
  for (const key of keys) if (typeof record[key] === "string" && record[key]) return String(record[key]);
  return null;
};

const buildAgentSummaries = (): AgentSummary[] => {
  const byId = new Map<string, AgentSummary>();
  const ensure = (agent: unknown, scenario: unknown, refs: { runId?: string; failureCaseId?: string; regressionId?: string; evaluationId?: string; decisionId?: string }) => {
    const agentId = agentText(agent, "agent_id", "agent_family") || "unknown-agent";
    const domain = agentText(agent, "agent_domain") || (agentId === "incident-remediation-agent" ? "Incident Remediation Agent" : "Production Change Agent");
    const current = byId.get(agentId) || {
      agentId,
      domain,
      agentType: agentText(agent, "agent_type") || (domain === "Incident Remediation Agent" ? "INCIDENT_REMEDIATION" : "STATEFUL_CHANGE"),
      contractId: agentText(agent, "agent_contract_id") || (agentId === "incident-remediation-agent" ? "incident-remediation-agent-contract" : "production-change-agent-contract"),
      versions: [], profiles: [], scenarioRefs: [], runIds: [], failureCaseIds: [], regressionIds: [], evaluationIds: [], decisionIds: [],
    };
    const version = agentText(agent, "agent_version", "known_bad_version");
    const profile = agentText(agent, "configuration_id");
    const scenarioRecord = scenario && typeof scenario === "object" && !Array.isArray(scenario) ? scenario as JsonRecord : null;
    if (version && !current.versions.includes(version)) current.versions.push(version);
    if (profile && !current.profiles.includes(profile)) current.profiles.push(profile);
    if (scenarioRecord && !current.scenarioRefs.some((item) => item.scenario_id === scenarioRecord.scenario_id && item.scenario_version === scenarioRecord.scenario_version && item.case_id === scenarioRecord.case_id)) current.scenarioRefs.push({ ...scenarioRecord });
    if (refs.runId && !current.runIds.includes(refs.runId)) current.runIds.push(refs.runId);
    if (refs.failureCaseId && !current.failureCaseIds.includes(refs.failureCaseId)) current.failureCaseIds.push(refs.failureCaseId);
    if (refs.regressionId && !current.regressionIds.includes(refs.regressionId)) current.regressionIds.push(refs.regressionId);
    if (refs.evaluationId && !current.evaluationIds.includes(refs.evaluationId)) current.evaluationIds.push(refs.evaluationId);
    if (refs.decisionId && !current.decisionIds.includes(refs.decisionId)) current.decisionIds.push(refs.decisionId);
    byId.set(agentId, current);
  };
  allReviewedRuns.forEach((run) => ensure(run.run.agent, run.scenario, { runId: run.run.runId }));
  reviewedFailureCases.forEach((item) => ensure(item.agent, item.scenario, { failureCaseId: item.failureCase.failureCaseId, runId: item.sourceRun.runId }));
  reviewedRegressions.forEach((item) => ensure(item.agent, item.scenario, { regressionId: item.regression.regressionId, failureCaseId: item.sourceFailureCase.failureCaseId }));
  reviewedEvaluations.forEach((item) => {
    ensure(item.evaluation.agent, undefined, { evaluationId: item.evaluation.evaluationId });
    item.evaluation.memberResults.forEach((member) => ensure(item.evaluation.agent, member.scenarioRef, { evaluationId: item.evaluation.evaluationId }));
  });
  reviewedReleaseDecisions.forEach((item) => ensure(item.releaseDecision.evaluatedAgent, undefined, { decisionId: item.releaseDecision.releaseDecisionId, evaluationId: String(item.releaseDecision.candidateEvaluationRef.evaluation_id || "") || undefined }));
  return [...byId.values()].sort((left, right) => left.domain.localeCompare(right.domain));
};

export let reviewedAgents: AgentSummary[] = buildAgentSummaries();

export interface ControlPlaneCorpusPayload {
  runs: unknown[];
  failures: unknown[];
  regressions: unknown[];
  regressionResults: unknown[];
  regressionCollections: unknown[];
  evaluationSuites: unknown[];
  evaluations: unknown[];
  comparisons: unknown[];
  qualityPolicies: unknown[];
  qualityGates: unknown[];
  releaseDecisions: unknown[];
}

const asCorpusList = (value: unknown): unknown[] => Array.isArray(value) ? value : value === null || value === undefined ? [] : [value];

/** Replace the fixture-backed snapshot only after every API artifact resolves and normalizes. */
export const activateControlPlaneCorpus = (payload: ControlPlaneCorpusPayload): void => {
  const runs = payload.runs.map(normalizeArtifact);
  const failures = payload.failures.map(normalizeFailureCase);
  const regressions = payload.regressions.map(normalizeRegression);
  const regressionResults = payload.regressionResults.map(normalizeRegressionResult);
  const evaluations = payload.evaluations.map(normalizeEvaluation);
  const qualityGates = payload.qualityGates.map(normalizeQualityGate);
  const decisions = payload.releaseDecisions.map(normalizeReleaseDecision);
  const suites = asCorpusList(payload.evaluationSuites).map(normalizeEvaluationSuite);
  const comparisons = asCorpusList(payload.comparisons).map(normalizeComparison);
  const policies = asCorpusList(payload.qualityPolicies).map(normalizeQualityPolicy);
  const collections = asCorpusList(payload.regressionCollections).map(normalizeRegressionCollection);
  const suite = suites[0];
  const comparison = comparisons[0];
  const policy = policies[0];
  const collection = collections[0];
  if (!suite || !comparison || !policy || !collection) throw new Error("Malformed Control Plane corpus: required aggregate missing");
  const evaluationRunIds = new Set(
    evaluations.flatMap((evaluation) => evaluation.evaluation.memberResults
      .map((member) => member.runRef.run_id)
      .filter((value): value is string => typeof value === "string")),
  );
  const evaluationRegressionResultIds = new Set(
    evaluations.flatMap((evaluation) => evaluation.evaluation.memberResults
      .map((member) => member.regressionResultRef?.result_id)
      .filter((value): value is string => typeof value === "string")),
  );
  const evaluationRuns = runs.filter((run) => evaluationRunIds.has(run.run.runId));
  const primaryRuns = runs.filter((run) => !evaluationRunIds.has(run.run.runId));
  const evaluationRegressionResults = regressionResults.filter((result) => evaluationRegressionResultIds.has(result.result.resultId));
  const primaryRegressionResults = regressionResults.filter((result) => !evaluationRegressionResultIds.has(result.result.resultId));

  reviewedRuns = primaryRuns;
  reviewedEvaluationRuns = evaluationRuns;
  reviewedFailureCases = failures;
  reviewedRegressions = regressions;
  reviewedRegressionResults = primaryRegressionResults;
  reviewedEvaluationRegressionResults = evaluationRegressionResults;
  reviewedRegressionCollection = collection;
  reviewedRegressionCollections = collections;
  reviewedEvaluationSuite = suite;
  reviewedEvaluationSuites = suites;
  reviewedEvaluations = evaluations;
  reviewedEvaluationComparison = comparison;
  reviewedEvaluationComparisons = comparisons;
  reviewedQualityPolicy = policy;
  reviewedQualityPolicies = policies;
  reviewedQualityGates = qualityGates;
  reviewedReleaseDecisions = decisions;
  allReviewedRuns = [...reviewedRuns, ...reviewedEvaluationRuns];
  allRegressionResults = [...reviewedRegressionResults, ...reviewedEvaluationRegressionResults];
  reviewedAgents = buildAgentSummaries();
};

export const getRun = (runId: string): RunEvidence | undefined => allReviewedRuns.find((run) => run.run.runId === runId);

export const isFaultedRun = (run: RunEvidence): boolean => run.fault.planned && run.fault.triggered;

export const isAgentFailureRun = (run: RunEvidence): boolean => run.outcome.status === "FAIL" && run.outcome.attribution === "Agent";

export const isEnvironmentErrorRun = (run: RunEvidence): boolean => run.outcome.status === "ERROR" && run.outcome.attribution === "Platform/Environment";

export const getFailureCase = (failureCaseId: string): FailureCase | undefined => reviewedFailureCases.find((item) => item.failureCase.failureCaseId === failureCaseId);

export const getFailureCaseForRun = (runId: string): FailureCase | undefined => reviewedFailureCases.find((item) => item.sourceRun.runId === runId || item.reproductionAttempts.some((attempt) => attempt.runId === runId));

export const getRegression = (regressionId: string): Regression | undefined => reviewedRegressions.find((item) => item.regression.regressionId === regressionId);

export const getRegressionResult = (resultId: string): RegressionExecutionResult | undefined => reviewedRegressionResults.find((item) => item.result.resultId === resultId);

export const getRegressionResults = (regressionId: string): RegressionExecutionResult[] => reviewedRegressionResults.filter((item) => item.result.regressionId === regressionId);

export const getRegressionResultForRun = (runId: string): RegressionExecutionResult | undefined => allRegressionResults.find((item) => item.result.runRef.run_id === runId);

export const getRegressionForRun = (runId: string): Regression | undefined => {
  const result = getRegressionResultForRun(runId);
  return result ? getRegression(result.result.regressionId) : undefined;
};

export const getEvaluation = (evaluationId: string): EvaluationResult | undefined => reviewedEvaluations.find((item) => item.evaluation.evaluationId === evaluationId);

export const getEvaluationComparison = (comparisonId: string): EvaluationComparison | undefined => reviewedEvaluationComparisons.find((item) => item.comparison.comparisonId === comparisonId);

export const getAgent = (agentId: string): AgentSummary | undefined => reviewedAgents.find((item) => item.agentId === agentId);

export const getQualityGate = (gateEvaluationId: string): QualityGateEvaluation | undefined => reviewedQualityGates.find((item) => item.gateEvaluation.gateEvaluationId === gateEvaluationId);

export const getReleaseDecision = (releaseDecisionId: string): ReleaseDecision | undefined => reviewedReleaseDecisions.find((item) => item.releaseDecision.releaseDecisionId === releaseDecisionId);

export const getUsage = (run: RunEvidence): JsonRecord => asOptionalObject(run.llmProvider.raw_usage, "llm_provider.raw_usage") || {};

export const getDerivedCost = (run: RunEvidence): JsonRecord => asOptionalObject(run.llmProvider.derived_cost, "llm_provider.derived_cost") || {};
