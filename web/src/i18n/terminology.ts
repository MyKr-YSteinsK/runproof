import type { Locale } from "./types";

export const KEEP_ENGLISH_TERMS = [
  "Agent", "Run", "Regression", "Baseline", "Candidate", "Evidence", "Timeline", "State Diff",
  "Trajectory Diff", "Release Gate", "Release Decision", "Failure Case", "Failure Intelligence",
  "Version Bisect", "Quality Policy", "Control Plane", "Worker", "Provider", "Scenario", "Artifact",
  "UNKNOWN_OUTCOME", "RECONCILE_REQUIRED", "PASS", "FAIL", "ERROR", "INVALID", "INCONCLUSIVE",
  "CANCELLED", "ELIGIBLE", "BLOCKED", "REVIEW_REQUIRED",
] as const;

export type TerminologyKey =
  | "failureAttribution"
  | "structuralFailureFamily"
  | "firstMeaningfulDivergence"
  | "evidenceAdequacy"
  | "validAgentTrials"
  | "confidenceInterval"
  | "zeroToleranceEvent"
  | "platformErrorRate"
  | "traceability"
  | "immutableEvidence";

const terminology: Record<TerminologyKey, Record<Locale, string>> = {
  failureAttribution: { "en-US": "Failure Attribution", "zh-CN": "失败归因（Failure Attribution）" },
  structuralFailureFamily: { "en-US": "Structural Failure Family", "zh-CN": "结构失败族（Structural Failure Family）" },
  firstMeaningfulDivergence: { "en-US": "First Meaningful Divergence", "zh-CN": "首次有效分歧（First Meaningful Divergence）" },
  evidenceAdequacy: { "en-US": "Evidence Adequacy", "zh-CN": "证据充分性（Evidence Adequacy）" },
  validAgentTrials: { "en-US": "Valid Agent Trials", "zh-CN": "有效 Agent 样本（Valid Agent Trials）" },
  confidenceInterval: { "en-US": "Confidence Interval", "zh-CN": "置信区间（Confidence Interval）" },
  zeroToleranceEvent: { "en-US": "Zero-tolerance Event", "zh-CN": "零容忍事件（Zero-tolerance Event）" },
  platformErrorRate: { "en-US": "Platform Error Rate", "zh-CN": "平台错误率（Platform Error Rate）" },
  traceability: { "en-US": "Traceability", "zh-CN": "可追溯性（Traceability）" },
  immutableEvidence: { "en-US": "Immutable Evidence", "zh-CN": "不可变证据（Immutable Evidence）" },
};

const statusDescriptions: Record<string, Record<Locale, string>> = {
  PASS: { "en-US": "passed", "zh-CN": "通过" },
  FAIL: { "en-US": "failed", "zh-CN": "未通过" },
  ERROR: { "en-US": "platform / environment error", "zh-CN": "平台 / 环境错误" },
  INVALID: { "en-US": "invalid evidence", "zh-CN": "证据无效" },
  INCONCLUSIVE: { "en-US": "evidence insufficient", "zh-CN": "证据不足" },
  CANCELLED: { "en-US": "cancelled", "zh-CN": "已取消" },
  ELIGIBLE: { "en-US": "eligible for release consideration", "zh-CN": "可进入发布评估" },
  BLOCKED: { "en-US": "blocked", "zh-CN": "已阻断" },
  REVIEW_REQUIRED: { "en-US": "human review required", "zh-CN": "需要人工复核" },
  UNKNOWN_OUTCOME: { "en-US": "outcome unknown", "zh-CN": "结果未知" },
  RECONCILE_REQUIRED: { "en-US": "reconciliation required", "zh-CN": "需要 reconcile" },
  OBSERVED_FLAKY: { "en-US": "flaky behavior observed", "zh-CN": "观察到 flaky 行为" },
  NO_CLEAR_DIFFERENCE: { "en-US": "no clear difference", "zh-CN": "没有明确差异" },
  IMPROVED: { "en-US": "improved", "zh-CN": "已改善" },
  REGRESSED: { "en-US": "regressed", "zh-CN": "已回归" },
  COMPLETE: { "en-US": "complete", "zh-CN": "已完成" },
  PROMOTED: { "en-US": "promoted", "zh-CN": "已 promotion" },
  VALIDATED: { "en-US": "validated", "zh-CN": "已验证" },
  BOUND: { "en-US": "bound", "zh-CN": "已绑定" },
  PENDING: { "en-US": "pending", "zh-CN": "待处理" },
};

export function terminologyLabel(locale: Locale, key: TerminologyKey): string {
  return terminology[key][locale];
}

export function statusDescription(locale: Locale, status: string): string | undefined {
  return statusDescriptions[status]?.[locale];
}

export function statusAccessibleLabel(locale: Locale, status: string): string {
  const description = statusDescription(locale, status);
  return description ? `${status} · ${description}` : status;
}
