import statisticalSamplingPlanStableArtifact from "../../../runtime/reviewed-rpf18-statistical-sampling-plan-stable.json";
import statisticalEvaluationStableArtifact from "../../../runtime/reviewed-rpf18-statistical-evaluation-stable.json";
import statisticalSamplingPlanBaselineArtifact from "../../../runtime/reviewed-rpf18-statistical-sampling-plan-baseline.json";
import statisticalEvaluationBaselineArtifact from "../../../runtime/reviewed-rpf18-statistical-evaluation-baseline.json";
import statisticalComparisonArtifact from "../../../runtime/reviewed-rpf18-statistical-comparison.json";
import statisticalPolicyArtifact from "../../../runtime/reviewed-rpf18-statistical-policy.json";
import statisticalGateStableArtifact from "../../../runtime/reviewed-rpf18-statistical-gate-stable.json";
import statisticalDecisionStableArtifact from "../../../runtime/reviewed-rpf18-statistical-decision-stable.json";
import statisticalSamplingPlanFlakyArtifact from "../../../runtime/reviewed-rpf18-statistical-sampling-plan-flaky.json";
import statisticalEvaluationFlakyArtifact from "../../../runtime/reviewed-rpf18-statistical-evaluation-flaky.json";
import statisticalGateFlakyArtifact from "../../../runtime/reviewed-rpf18-statistical-gate-flaky.json";
import statisticalDecisionFlakyArtifact from "../../../runtime/reviewed-rpf18-statistical-decision-flaky.json";
import statisticalSamplingPlanSafetyArtifact from "../../../runtime/reviewed-rpf18-statistical-sampling-plan-safety.json";
import statisticalEvaluationSafetyArtifact from "../../../runtime/reviewed-rpf18-statistical-evaluation-safety.json";
import statisticalGateSafetyArtifact from "../../../runtime/reviewed-rpf18-statistical-gate-safety.json";
import statisticalDecisionSafetyArtifact from "../../../runtime/reviewed-rpf18-statistical-decision-safety.json";
import statisticalSamplingPlanEvidencePoorArtifact from "../../../runtime/reviewed-rpf18-statistical-sampling-plan-evidence-poor.json";
import statisticalEvaluationEvidencePoorArtifact from "../../../runtime/reviewed-rpf18-statistical-evaluation-evidence-poor.json";
import statisticalGateEvidencePoorArtifact from "../../../runtime/reviewed-rpf18-statistical-gate-evidence-poor.json";
import statisticalDecisionEvidencePoorArtifact from "../../../runtime/reviewed-rpf18-statistical-decision-evidence-poor.json";
import type { JsonRecord } from "./artifacts";

export interface StatisticalSamplingPlan {
  schemaVersion: string;
  artifactKind: string;
  samplingPlan: {
    samplingPlanId: string;
    samplingPlanVersion: string;
    candidateIdentity: string;
    suiteRef: JsonRecord;
    agent: JsonRecord;
    scenarioRef: JsonRecord;
    requestedTrialCount: number;
    minimumValidTrialCount: number;
    maximumAttemptBudget: number;
    confidence: JsonRecord;
    trialIsolation: JsonRecord;
    stochasticProfile: JsonRecord;
    controlledBehaviorSequence: string[];
    sourceIdentity: JsonRecord;
    raw: JsonRecord;
  };
}

export interface StatisticalTrial {
  trialId: string;
  trialIndex: number;
  outcome: string;
  sourceRunOutcome: string;
  agentQualityEligible: boolean;
  evidenceValid: boolean;
  runRef: JsonRecord | null;
  environmentRef: JsonRecord | null;
  failureIntelligence: JsonRecord | null;
  zeroToleranceEvents: JsonRecord[];
  metrics: JsonRecord;
  regressionCovered: boolean;
  controlledBehavior: string;
  raw: JsonRecord;
}

export interface StatisticalEvaluation {
  schemaVersion: string;
  artifactKind: string;
  statisticalEvaluation: {
    evaluationId: string;
    evaluationVersion: string;
    evaluationStatus: string;
    samplingPlanRef: JsonRecord;
    samplingPlanIdentity: string;
    candidateIdentity: string;
    agent: JsonRecord;
    scenarioRef: JsonRecord;
    trials: StatisticalTrial[];
    attemptedTrialCount: number;
    requestedTrialCount: number;
    outcomeCounts: Record<string, number>;
    validAgentTrialCount: number;
    summary: JsonRecord;
    sourceIdentity: JsonRecord;
    raw: JsonRecord;
  };
}

export interface StatisticalComparison {
  schemaVersion: string;
  artifactKind: string;
  statisticalComparison: {
    comparisonId: string;
    status: string;
    baselineRef: JsonRecord;
    candidateRef: JsonRecord;
    aggregate: JsonRecord;
    sourceIdentity: JsonRecord;
    raw: JsonRecord;
  };
}

export interface StatisticalPolicy {
  schemaVersion: string;
  artifactKind: string;
  statisticalPolicy: {
    policyId: string;
    policyVersion: string;
    policyIdentity: string;
    decisionPrecedence: string[];
    rules: JsonRecord;
    sourceIdentity: JsonRecord;
    raw: JsonRecord;
  };
}

export interface StatisticalGate {
  schemaVersion: string;
  artifactKind: string;
  statisticalGate: {
    gateEvaluationId: string;
    status: string;
    decisionStatus: string;
    samplingPlanRef: JsonRecord;
    evaluationRef: JsonRecord;
    comparisonRef: JsonRecord | null;
    ruleResults: JsonRecord[];
    blockingReasons: JsonRecord[];
    evidenceGapReasons: JsonRecord[];
    reviewReasons: JsonRecord[];
    summaryFacts: JsonRecord;
    authorizationBoundary: JsonRecord;
    sourceIdentity: JsonRecord;
    raw: JsonRecord;
  };
}

export interface StatisticalDecision {
  schemaVersion: string;
  artifactKind: string;
  statisticalReleaseDecision: {
    releaseDecisionId: string;
    decisionStatus: string;
    samplingPlanRef: JsonRecord;
    evaluationRef: JsonRecord;
    comparisonRef: JsonRecord | null;
    explanation: string[];
    ruleResults: JsonRecord[];
    authorizationBoundary: JsonRecord;
    raw: JsonRecord;
  };
}

const asObject = (value: unknown, label: string): JsonRecord => {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`Malformed statistical artifact: ${label}`);
  return value as JsonRecord;
};

const asString = (value: unknown, label: string): string => {
  if (typeof value !== "string" || !value) throw new Error(`Malformed statistical artifact: ${label}`);
  return value;
};

const asNumber = (value: unknown, label: string): number => {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`Malformed statistical artifact: ${label}`);
  return value;
};

const asBoolean = (value: unknown, label: string): boolean => {
  if (typeof value !== "boolean") throw new Error(`Malformed statistical artifact: ${label}`);
  return value;
};

const asArray = (value: unknown, label: string): unknown[] => {
  if (!Array.isArray(value)) throw new Error(`Malformed statistical artifact: ${label}`);
  return value;
};

const optionalObject = (value: unknown, label: string): JsonRecord | null => value === null || value === undefined ? null : asObject(value, label);

export const normalizeStatisticalSamplingPlan = (raw: unknown): StatisticalSamplingPlan => {
  const artifact = asObject(raw, "sampling plan");
  const plan = asObject(artifact.sampling_plan, "sampling_plan");
  return {
    schemaVersion: asString(artifact.schema_version, "sampling_plan.schema_version"),
    artifactKind: asString(artifact.artifact_kind, "sampling_plan.artifact_kind"),
    samplingPlan: {
      samplingPlanId: asString(plan.sampling_plan_id, "sampling_plan_id"),
      samplingPlanVersion: asString(plan.sampling_plan_version, "sampling_plan_version"),
      candidateIdentity: asString(plan.candidate_identity, "candidate_identity"),
      suiteRef: asObject(plan.suite_ref, "suite_ref"),
      agent: asObject(plan.agent, "agent"),
      scenarioRef: asObject(plan.scenario_ref, "scenario_ref"),
      requestedTrialCount: asNumber(plan.requested_trial_count, "requested_trial_count"),
      minimumValidTrialCount: asNumber(plan.minimum_valid_trial_count, "minimum_valid_trial_count"),
      maximumAttemptBudget: asNumber(plan.maximum_attempt_budget, "maximum_attempt_budget"),
      confidence: asObject(plan.confidence, "confidence"),
      trialIsolation: asObject(plan.trial_isolation, "trial_isolation"),
      stochasticProfile: asObject(plan.stochastic_profile, "stochastic_profile"),
      controlledBehaviorSequence: asArray(plan.controlled_behavior_sequence, "controlled_behavior_sequence").map((value) => asString(value, "controlled_behavior_sequence item")),
      sourceIdentity: asObject(plan.source_identity, "source_identity"),
      raw: plan,
    },
  };
};

const normalizeTrial = (raw: unknown): StatisticalTrial => {
  const trial = asObject(raw, "trial");
  return {
    trialId: asString(trial.trial_id, "trial_id"),
    trialIndex: asNumber(trial.trial_index, "trial_index"),
    outcome: asString(trial.outcome, "trial.outcome"),
    sourceRunOutcome: asString(trial.source_run_outcome, "source_run_outcome"),
    agentQualityEligible: asBoolean(trial.agent_quality_eligible, "agent_quality_eligible"),
    evidenceValid: asBoolean(trial.evidence_valid, "evidence_valid"),
    runRef: optionalObject(trial.run_ref, "run_ref"),
    environmentRef: optionalObject(trial.environment_ref, "environment_ref"),
    failureIntelligence: optionalObject(trial.failure_intelligence, "failure_intelligence"),
    zeroToleranceEvents: asArray(trial.zero_tolerance_events, "zero_tolerance_events").map((value) => asObject(value, "zero_tolerance_event")),
    metrics: asObject(trial.metrics, "metrics"),
    regressionCovered: asBoolean(trial.regression_covered, "regression_covered"),
    controlledBehavior: typeof trial.controlled_behavior === "string" ? trial.controlled_behavior : "UNSPECIFIED",
    raw: trial,
  };
};

export const normalizeStatisticalEvaluation = (raw: unknown): StatisticalEvaluation => {
  const artifact = asObject(raw, "statistical evaluation");
  const evaluation = asObject(artifact.statistical_evaluation, "statistical_evaluation");
  const counts = asObject(evaluation.outcome_counts, "outcome_counts");
  return {
    schemaVersion: asString(artifact.schema_version, "statistical_evaluation.schema_version"),
    artifactKind: asString(artifact.artifact_kind, "statistical_evaluation.artifact_kind"),
    statisticalEvaluation: {
      evaluationId: asString(evaluation.evaluation_id, "evaluation_id"),
      evaluationVersion: asString(evaluation.evaluation_version, "evaluation_version"),
      evaluationStatus: asString(evaluation.evaluation_status, "evaluation_status"),
      samplingPlanRef: asObject(evaluation.sampling_plan_ref, "sampling_plan_ref"),
      samplingPlanIdentity: asString(evaluation.sampling_plan_identity, "sampling_plan_identity"),
      candidateIdentity: asString(evaluation.candidate_identity, "candidate_identity"),
      agent: asObject(evaluation.agent, "agent"),
      scenarioRef: asObject(evaluation.scenario_ref, "scenario_ref"),
      trials: asArray(evaluation.trials, "trials").map(normalizeTrial),
      attemptedTrialCount: asNumber(evaluation.attempted_trial_count, "attempted_trial_count"),
      requestedTrialCount: asNumber(evaluation.requested_trial_count, "requested_trial_count"),
      outcomeCounts: Object.fromEntries(Object.entries(counts).map(([key, value]) => [key, asNumber(value, `outcome_counts.${key}`)])),
      validAgentTrialCount: asNumber(evaluation.valid_agent_trial_count, "valid_agent_trial_count"),
      summary: asObject(evaluation.summary, "summary"),
      sourceIdentity: asObject(evaluation.source_identity, "source_identity"),
      raw: evaluation,
    },
  };
};

export const normalizeStatisticalComparison = (raw: unknown): StatisticalComparison => {
  const artifact = asObject(raw, "statistical comparison");
  const comparison = asObject(artifact.statistical_comparison, "statistical_comparison");
  return {
    schemaVersion: asString(artifact.schema_version, "statistical_comparison.schema_version"),
    artifactKind: asString(artifact.artifact_kind, "statistical_comparison.artifact_kind"),
    statisticalComparison: {
      comparisonId: asString(comparison.comparison_id, "comparison_id"),
      status: asString(comparison.status, "status"),
      baselineRef: asObject(comparison.baseline_ref, "baseline_ref"),
      candidateRef: asObject(comparison.candidate_ref, "candidate_ref"),
      aggregate: asObject(comparison.aggregate, "aggregate"),
      sourceIdentity: asObject(comparison.source_identity, "source_identity"),
      raw: comparison,
    },
  };
};

export const normalizeStatisticalPolicy = (raw: unknown): StatisticalPolicy => {
  const artifact = asObject(raw, "statistical policy");
  const policy = asObject(artifact.statistical_policy, "statistical_policy");
  return {
    schemaVersion: asString(artifact.schema_version, "statistical_policy.schema_version"),
    artifactKind: asString(artifact.artifact_kind, "statistical_policy.artifact_kind"),
    statisticalPolicy: {
      policyId: asString(policy.policy_id, "policy_id"),
      policyVersion: asString(policy.policy_version, "policy_version"),
      policyIdentity: asString(policy.policy_identity, "policy_identity"),
      decisionPrecedence: asArray(policy.decision_precedence, "decision_precedence").map((value) => asString(value, "decision precedence item")),
      rules: asObject(policy.rules, "rules"),
      sourceIdentity: asObject(policy.source_identity, "source_identity"),
      raw: policy,
    },
  };
};

export const normalizeStatisticalGate = (raw: unknown): StatisticalGate => {
  const artifact = asObject(raw, "statistical gate");
  const gate = asObject(artifact.statistical_gate, "statistical_gate");
  return {
    schemaVersion: asString(artifact.schema_version, "statistical_gate.schema_version"),
    artifactKind: asString(artifact.artifact_kind, "statistical_gate.artifact_kind"),
    statisticalGate: {
      gateEvaluationId: asString(gate.gate_evaluation_id, "gate_evaluation_id"),
      status: asString(gate.status, "status"),
      decisionStatus: asString(gate.decision_status, "decision_status"),
      samplingPlanRef: asObject(gate.sampling_plan_ref, "sampling_plan_ref"),
      evaluationRef: asObject(gate.evaluation_ref, "evaluation_ref"),
      comparisonRef: optionalObject(gate.comparison_ref, "comparison_ref"),
      ruleResults: asArray(gate.rule_results, "rule_results").map((value) => asObject(value, "rule result")),
      blockingReasons: asArray(gate.blocking_reasons, "blocking_reasons").map((value) => asObject(value, "blocking reason")),
      evidenceGapReasons: asArray(gate.evidence_gap_reasons, "evidence_gap_reasons").map((value) => asObject(value, "evidence gap reason")),
      reviewReasons: asArray(gate.review_reasons, "review_reasons").map((value) => asObject(value, "review reason")),
      summaryFacts: asObject(gate.summary_facts, "summary_facts"),
      authorizationBoundary: asObject(gate.authorization_boundary, "authorization_boundary"),
      sourceIdentity: asObject(gate.source_identity, "source_identity"),
      raw: gate,
    },
  };
};

export const normalizeStatisticalDecision = (raw: unknown): StatisticalDecision => {
  const artifact = asObject(raw, "statistical release decision");
  const decision = asObject(artifact.statistical_release_decision, "statistical_release_decision");
  return {
    schemaVersion: asString(artifact.schema_version, "statistical_release_decision.schema_version"),
    artifactKind: asString(artifact.artifact_kind, "statistical_release_decision.artifact_kind"),
    statisticalReleaseDecision: {
      releaseDecisionId: asString(decision.release_decision_id, "release_decision_id"),
      decisionStatus: asString(decision.decision_status, "decision_status"),
      samplingPlanRef: asObject(decision.sampling_plan_ref, "sampling_plan_ref"),
      evaluationRef: asObject(decision.evaluation_ref, "evaluation_ref"),
      comparisonRef: optionalObject(decision.comparison_ref, "comparison_ref"),
      explanation: asArray(decision.explanation, "explanation").map((value) => asString(value, "explanation item")),
      ruleResults: asArray(decision.rule_results, "rule_results").map((value) => asObject(value, "rule result")),
      authorizationBoundary: asObject(decision.authorization_boundary, "authorization_boundary"),
      raw: decision,
    },
  };
};

export let reviewedStatisticalSamplingPlans: StatisticalSamplingPlan[] = [
  normalizeStatisticalSamplingPlan(statisticalSamplingPlanStableArtifact),
  normalizeStatisticalSamplingPlan(statisticalSamplingPlanBaselineArtifact),
  normalizeStatisticalSamplingPlan(statisticalSamplingPlanFlakyArtifact),
  normalizeStatisticalSamplingPlan(statisticalSamplingPlanSafetyArtifact),
  normalizeStatisticalSamplingPlan(statisticalSamplingPlanEvidencePoorArtifact),
];
export let reviewedStatisticalEvaluations: StatisticalEvaluation[] = [
  normalizeStatisticalEvaluation(statisticalEvaluationStableArtifact),
  normalizeStatisticalEvaluation(statisticalEvaluationBaselineArtifact),
  normalizeStatisticalEvaluation(statisticalEvaluationFlakyArtifact),
  normalizeStatisticalEvaluation(statisticalEvaluationSafetyArtifact),
  normalizeStatisticalEvaluation(statisticalEvaluationEvidencePoorArtifact),
];
export let reviewedStatisticalComparisons: StatisticalComparison[] = [normalizeStatisticalComparison(statisticalComparisonArtifact)];
export let reviewedStatisticalPolicies: StatisticalPolicy[] = [normalizeStatisticalPolicy(statisticalPolicyArtifact)];
export let reviewedStatisticalGates: StatisticalGate[] = [
  normalizeStatisticalGate(statisticalGateStableArtifact),
  normalizeStatisticalGate(statisticalGateFlakyArtifact),
  normalizeStatisticalGate(statisticalGateSafetyArtifact),
  normalizeStatisticalGate(statisticalGateEvidencePoorArtifact),
];
export let reviewedStatisticalDecisions: StatisticalDecision[] = [
  normalizeStatisticalDecision(statisticalDecisionStableArtifact),
  normalizeStatisticalDecision(statisticalDecisionFlakyArtifact),
  normalizeStatisticalDecision(statisticalDecisionSafetyArtifact),
  normalizeStatisticalDecision(statisticalDecisionEvidencePoorArtifact),
];

export interface StatisticalCorpusPayload {
  samplingPlans: unknown[];
  evaluations: unknown[];
  comparisons: unknown[];
  policies: unknown[];
  gates: unknown[];
  decisions: unknown[];
}

export const activateStatisticalCorpus = (payload: StatisticalCorpusPayload): void => {
  const plans = payload.samplingPlans.map(normalizeStatisticalSamplingPlan);
  const evaluations = payload.evaluations.map(normalizeStatisticalEvaluation);
  const comparisons = payload.comparisons.map(normalizeStatisticalComparison);
  const policies = payload.policies.map(normalizeStatisticalPolicy);
  const gates = payload.gates.map(normalizeStatisticalGate);
  const decisions = payload.decisions.map(normalizeStatisticalDecision);
  if (!plans.length || !evaluations.length || !comparisons.length || !policies.length || !gates.length || !decisions.length) {
    throw new Error("Malformed Control Plane corpus: statistical corpus incomplete");
  }
  reviewedStatisticalSamplingPlans = plans;
  reviewedStatisticalEvaluations = evaluations;
  reviewedStatisticalComparisons = comparisons;
  reviewedStatisticalPolicies = policies;
  reviewedStatisticalGates = gates;
  reviewedStatisticalDecisions = decisions;
};

export const getStatisticalSamplingPlan = (id: string): StatisticalSamplingPlan | undefined => reviewedStatisticalSamplingPlans.find((item) => item.samplingPlan.samplingPlanId === id);
export const getStatisticalEvaluation = (id: string): StatisticalEvaluation | undefined => reviewedStatisticalEvaluations.find((item) => item.statisticalEvaluation.evaluationId === id);
export const getStatisticalComparison = (id: string): StatisticalComparison | undefined => reviewedStatisticalComparisons.find((item) => item.statisticalComparison.comparisonId === id);
export const getStatisticalGateForEvaluation = (id: string): StatisticalGate | undefined => reviewedStatisticalGates.find((item) => item.statisticalGate.evaluationRef.evaluation_id === id);
export const getStatisticalDecisionForEvaluation = (id: string): StatisticalDecision | undefined => reviewedStatisticalDecisions.find((item) => item.statisticalReleaseDecision.evaluationRef.evaluation_id === id);
