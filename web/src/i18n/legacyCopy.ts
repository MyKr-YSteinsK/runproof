import { messages } from "./messages";
import type { Locale } from "./types";

type CopyPair = readonly [string, string];

// Compatibility copy for the pre-RPF-25 read-only surfaces that still live in
// App.tsx. It is presentation-only: identifiers, enums, raw JSON, and mono
// evidence values are deliberately excluded by the DOM bridge.
const LEGACY_COPY: CopyPair[] = [
  ["RUN EVIDENCE · REVIEWED CORPUS", "RUN EVIDENCE · REVIEWED CORPUS|运行证据 · REVIEWED CORPUS"],
  ["Investigate a run from the evidence trail.", "从证据轨迹调查一个 Run。"],
  ["A compact control plane for reconstructing Agent behavior, environment transitions, and verified outcomes.", "用于重建 Agent 行为、Environment transition 与已验证结果的紧凑 Control Plane。"],
  ["ACTIVE CORPUS", "ACTIVE CORPUS|当前 corpus"],
  ["v2 schema · source-bound", "v2 schema · source-bound|v2 schema · 已绑定 source"],
  ["Evidence boundary.", "Evidence boundary · 证据边界。"],
  ["Failure Case investigation", "Failure Case investigation · Failure Case 调查"],
  ["Promoted Agent failure · source and reproduction evidence remain linked", "已 promotion 的 Agent failure · source 与 reproduction evidence 保持关联"],
  ["Historical Regression", "Historical Regression · 历史 Regression"],
  ["Known-bad FAIL reproduced · fixed Candidate PASS · not a Release decision", "已复现 known-bad FAIL · fixed Candidate PASS · 不是 Release Decision"],
  ["SELECT A RUN", "选择一个 Run"],
  ["Reviewed run evidence", "Reviewed Run Evidence"],
  ["Reviewed Run Evidence", "Reviewed run evidence|已审查 Run Evidence"],
  ["OUTCOME / SIGNAL", "OUTCOME / SIGNAL|结果 / 信号"],
  ["AGENT / SCENARIO", "AGENT / SCENARIO|Agent / Scenario"],
  ["PROVIDER / ENVIRONMENT", "PROVIDER / ENVIRONMENT|Provider / Environment"],
  ["RUN / COST", "RUN / COST|Run / Cost"],
  ["Read-only API adapter · no live run action", "只读 API adapter · 不执行 live Run"],
  ["RUN INVESTIGATION", "RUN INVESTIGATION · Run 调查"],
  ["Agent safety failure", "Agent safety failure · Agent 安全 failure"],
  ["Environment readiness error", "Environment readiness error · Environment readiness error"],
  ["Response-lost recovery run", "Response-lost recovery Run · response 丢失恢复 Run"],
  ["Normal release transition", "Normal release transition · 正常 release transition"],
  ["Run context identity", "Run context identity · Run 上下文 identity"],
  ["Timeline", "Timeline"],
  ["State diff", "State Diff"],
  ["Invariants & evidence", "Invariants & Evidence"],
  ["No Agent state diff", "没有 Agent State Diff"],
  ["No Agent invariant checks ran because the Environment failed before Agent start.", "Environment 在 Agent 启动前失败，因此没有执行 Agent invariant checks。"],
  ["Usage fact", "Usage fact · Usage 事实"],
  ["Derived value", "Derived Value"],
  ["tokens", "tokens"],
  ["AGENTS · CROSS-AGENT REGISTRY", "AGENTS · CROSS-AGENT REGISTRY"],
  ["Follow reliability by Agent identity.", "按 Agent identity 追踪可靠性。"],
  ["REGISTERED AGENTS", "REGISTERED AGENTS · 已注册 Agents"],
  ["explicit reviewed adapters", "显式 reviewed adapters"],
  ["Integration boundary.", "Integration boundary · 集成边界。"],
  ["Registered Agents", "Registered Agents · 已注册 Agents"],
  ["read-only contract view", "只读 contract 视图"],
  ["Scenario, tools, environment, verifier", "Scenario、tools、Environment、verifier"],
  ["Reviewed configurations", "Reviewed configurations · 已审查配置"],
  ["Quality outcome", "Quality outcome · Quality 结果"],
  ["Open linked Runs and Regressions", "打开关联的 Runs 与 Regressions"],
  ["No decision record linked.", "没有关联的 Decision 记录。"],
  ["REGRESSIONS · HISTORICAL CORPUS", "REGRESSIONS · HISTORICAL CORPUS"],
  ["Make a validated failure reusable.", "让已验证的 failure 可复用。"],
  ["Historical Regressions preserve the failure contract, promotion evidence, and focused rerun results as a small read-only test corpus.", "Historical Regressions 将 failure contract、promotion evidence 与 focused rerun results 保留为小型只读测试 corpus。"],
  ["ACTIVE COLLECTION", "ACTIVE COLLECTION · 当前 collection"],
  ["versioned collections · not Release", "个版本化 collection · 不是 Release"],
  ["Regression boundary.", "Regression boundary · Regression 边界。"],
  ["SELECT A REGRESSION", "选择一个 Regression"],
  ["Historical Regression collection", "Historical Regression collection"],
  ["STATUS / IDENTITY", "STATUS / IDENTITY|状态 / identity"],
  ["SCENARIO / INVARIANT", "SCENARIO / INVARIANT|Scenario / invariant"],
  ["KNOWN-BAD", "KNOWN-BAD"],
  ["FIXED CANDIDATE", "FIXED CANDIDATE"],
  ["EVALUATIONS · REVIEWED CORPUS", "EVALUATIONS · REVIEWED CORPUS"],
  ["Measure Agent quality across a controlled Suite.", "在受控 Suite 中衡量 Agent Quality。"],
  ["ACTIVE SUITES", "ACTIVE SUITES · 当前 Suites"],
  ["Evaluation boundary.", "Evaluation boundary · Evaluation 边界。"],
  ["SELECT AN EVALUATION", "选择一个 Evaluation"],
  ["Reviewed Evaluations", "Reviewed Evaluations"],
  ["COMPARISONS · REVIEWED CORPUS", "COMPARISONS · REVIEWED CORPUS"],
  ["See what changed between versions.", "查看版本之间发生了什么变化。"],
  ["RELEASE DECISIONS · REVIEWED CORPUS", "RELEASE DECISIONS · REVIEWED CORPUS"],
  ["Turn evidence into a bounded decision.", "将 Evidence 变成有边界的 Decision。"],
  ["ACTIVE POLICY", "ACTIVE POLICY · 当前 Policy"],
  ["Release boundary.", "Release boundary · Release 边界。"],
  ["FAILURE INTELLIGENCE · DETERMINISTIC CORPUS", "FAILURE INTELLIGENCE · DETERMINISTIC CORPUS"],
  ["Group failures by deterministic responsibility and structure.", "按确定性责任与结构聚合 failures。"],
  ["SELECT A FAILURE CLUSTER", "选择一个 Failure Cluster"],
  ["Version Bisect", "Version Bisect"],
  ["Locate the first bad version without rewriting history.", "在不改写历史的前提下定位 first bad version。"],
  ["FAILURE CASES · REVIEWED CORPUS", "FAILURE CASES · REVIEWED CORPUS"],
  ["Turn a real Agent failure into reusable evidence.", "将真实 Agent failure 变成可复用 Evidence。"],
  ["SELECT A FAILURE CASE", "选择一个 Failure Case"],
  ["DURABLE EXECUTIONS · POSTGRESQL READ MODEL", "DURABLE EXECUTIONS · POSTGRESQL READ MODEL"],
  ["Follow a job across attempts, leases, and evidence.", "跨 Attempts、leases 与 Evidence 追踪一个 Job。"],
  ["CURRENT VIEW", "CURRENT VIEW · 当前视图"],
  ["API only", "仅 API"],
  ["fixture mode has no jobs", "fixture 模式没有 Jobs"],
  ["canonical job snapshots", "canonical Job snapshots"],
  ["Execution boundary.", "Execution boundary · Execution 边界。"],
  ["EXPLICIT FIXTURE MODE", "EXPLICIT FIXTURE MODE · 显式 fixture 模式"],
  ["Durable jobs are available from the Control Plane API.", "Durable Jobs 可从 Control Plane API 获取。"],
  ["Canonical execution jobs", "Canonical execution Jobs"],
  ["No durable jobs in the current Control Plane.", "当前 Control Plane 没有 durable Jobs。"],
  ["DURABLE EXECUTION INVESTIGATION", "DURABLE EXECUTION INVESTIGATION"],
  ["APPEND-ONLY HISTORY", "APPEND-ONLY HISTORY"],
  ["Attempts and lease changes", "Attempts 与 lease 变化"],
  ["SIDE-EFFECT IDENTITY", "SIDE-EFFECT IDENTITY"],
  ["Operations and reconcile status", "Operations 与 reconcile 状态"],
  ["IMMUTABLE REFERENCES", "IMMUTABLE REFERENCES"],
  ["Terminal and execution evidence", "Terminal 与 Execution Evidence"],
  ["TRANSITION AUDIT", "TRANSITION AUDIT"],
  ["Append-only event history", "Append-only Event history"],
  ["The corpus contains normal PASS, recovered faulted PASS, deterministic Agent FAIL, and Platform/Environment ERROR. Failure Cases are separate artifacts; historical v1 evidence remains preserved.", "该 corpus 包含正常 PASS、已恢复的 faulted PASS、确定性的 Agent FAIL 与 Platform/Environment ERROR。Failure Cases 是独立 artifacts；历史 v1 evidence 保持保留。"],
  ["Evidence boundary.", "证据边界（Evidence boundary）。"],
  ["Normal transition · verified PASS", "正常 transition · 已验证 PASS"],
  ["Fault observed · reconciled PASS", "观察到 fault · reconcile 后 PASS"],
  ["Agent behavior defect · Failure Case", "Agent 行为 defect · Failure Case"],
  ["Platform/Environment · Agent not started", "Platform/Environment · Agent 尚未启动"],
  ["Agent detail", "Agent 详情"],
  ["AGENT DETAIL", "AGENT 详情"],
  ["This view binds versions and execution evidence to one explicit Agent contract. Production Change history remains independent from Incident Remediation history.", "此界面将版本与执行 evidence 绑定到一个显式 Agent contract。Production Change history 与 Incident Remediation history 保持独立。"],
  ["Agent contract identity", "Agent contract identity · Agent contract identity"],
  ["AGENT DOMAIN", "AGENT DOMAIN · Agent 领域"],
  ["AGENT TYPE", "AGENT TYPE · Agent 类型"],
  ["CONTRACT", "CONTRACT"],
  ["VERSIONS", "VERSIONS · 版本"],
  ["PROFILES", "PROFILES · Profiles"],
  ["Scenario refs", "Scenario refs"],
  ["Supported execution", "Supported execution · 支持的执行方式"],
  ["Evidence boundary", "Evidence boundary · 证据边界"],
  ["Authority", "Authority · 权限边界"],
  ["linked immutable Runs", "关联的不可变 Runs"],
  ["investigated Agent failures", "已调查的 Agent failures"],
  ["Baseline / Candidate aggregates", "Baseline / Candidate aggregates"],
  ["decision-only quality records", "仅 Decision 的质量记录"],
  ["LATEST DECISION", "LATEST DECISION · 最近 Decision"],
  ["EXECUTION EVIDENCE", "EXECUTION EVIDENCE · 执行 Evidence"],
  ["RUN · ", "RUN · "],
  ["REGRESSION · ", "REGRESSION · "],
  ["SELECTED EVIDENCE", "SELECTED EVIDENCE · 已选择 Evidence"],
  ["Evidence detail", "Evidence detail · Evidence 详情"],
  ["Show raw event payload", "显示 raw event payload"],
  ["Environment provisioned", "Environment 已 provisioned"],
  ["A fresh controlled environment was created.", "已创建 fresh controlled Environment。"],
  ["Readiness gate", "Readiness gate"],
  ["The environment reported ready before the run began.", "Run 开始前 Environment 报告 ready。"],
  ["Initial state verified", "Initial state verified"],
  ["The known starting state passed its verification gate.", "已知 starting state 通过 verification gate。"],
  ["Agent tool intent", "Agent tool intent"],
  ["The Agent selected a typed tool call.", "Agent 选择了 typed tool call。"],
  ["Tool result", "Tool result"],
  ["The tool boundary returned an observable result.", "Tool boundary 返回了可观察 result。"],
  ["Environment transition", "Environment transition"],
  ["The controlled environment recorded a state transition.", "受控 Environment 记录了 state transition。"],
  ["Fault observed", "Fault observed"],
  ["The planned fault crossed the Agent boundary.", "planned fault 穿过 Agent boundary。"],
  ["Reconcile", "Reconcile"],
  ["The uncertain operation was reconciled against receipt and state.", "不确定 operation 已依据 receipt 与 state 完成 reconcile。"],
  ["Agent completion", "Agent completion"],
  ["The Agent stopped after the required observations.", "Agent 在完成必要 observations 后停止。"],
  ["Actual state read-back", "Actual state read-back"],
  ["The final state was independently read back for verification.", "final state 已独立 read back 进行 verification。"],
  ["Environment cleanup", "Environment cleanup"],
  ["The run environment was removed and cleanup was checked.", "Run Environment 已移除并检查 cleanup。"],
  ["Tool execution failure", "Tool execution failure"],
  ["The harness classified a tool execution failure.", "harness 将 tool execution failure 分类。"],
  ["State observed after failure", "State observed after failure"],
  ["The harness observed state after a terminal failure.", "harness 在 terminal failure 后观察了 state。"],
  ["Safety guard blocked", "Safety guard blocked"],
  ["The runtime guard rejected an unsafe Agent action before side effect.", "runtime guard 在 side effect 前拒绝了不安全的 Agent action。"],
  ["Execution data is unavailable.", "Execution data 暂不可用。"],
  ["Loading durable job…", "正在加载 durable Job…"],
  ["Execution data is API-only.", "Execution data 仅支持 API。"],
  ["The Web surface did not receive a canonical execution response. It does not invent a fixture or retry a mutation.", "Web 界面没有收到 canonical execution response，不会伪造 fixture 或重试 mutation。"],
  ["Use the Control Plane read API to inspect PostgreSQL-backed jobs, attempts, operations, evidence refs, and events.", "请使用 Control Plane read API 检查 PostgreSQL-backed Jobs、Attempts、Operations、Evidence refs 与 Events。"],
];

const pairs = new Map(LEGACY_COPY.map(([key, value]) => {
  const [explicitEn, explicitZh] = value.split("|");
  return [key, { "en-US": explicitZh ? explicitEn : key, "zh-CN": explicitZh || explicitEn } as Record<Locale, string>];
}));

// Some pre-RPF-25 JSX blocks intentionally keep the semantic sentence split
// across text nodes and strong tags. These fragments are still presentation
// copy, so translate only the known phrases; identifiers, enums and evidence
// payloads never enter this table.
const FRAGMENT_COPY: readonly (readonly [string, string])[] = [
  ["Source:", "来源："],
  ["Read-only registry", "只读 registry"],
  ["no mutation or release action", "不执行 mutation 或 release action"],
  ["Read-only API adapter", "只读 API adapter"],
  ["no rerun or release action", "不执行 rerun 或 release action"],
  ["no execute or release action", "不执行 execute 或 release action"],
  ["no release/deploy action", "不执行 release/deploy action"],
  ["Read-only investigation", "只读调查"],
  ["no promote, rerun, or release action", "不执行 promote、rerun 或 release action"],
  ["no comparison mutation or release action", "不执行 comparison mutation 或 release action"],
  ["no promote action", "不执行 promote action"],
  ["no worker or release action", "不执行 worker 或 release action"],
  ["The corpus contains normal", "该 corpus 包含正常"],
  ["recovered faulted", "已恢复的 faulted"],
  ["deterministic Agent", "确定性的 Agent"],
  ["Failure Cases are separate artifacts", "Failure Cases 是独立 artifacts"],
  ["historical v1 evidence remains preserved", "历史 v1 evidence 保持保留"],
  ["Reviewed run evidence", "已审查 Run Evidence"],
  ["Run context identity", "Run 上下文 identity"],
  ["Evidence detail", "Evidence 详情"],
  ["Read-only · no worker or release action", "只读 · 不执行 worker 或 release action"],
  ["Read-only · no comparison mutation or release action", "只读 · 不执行 comparison mutation 或 release action"],
];

const normalizedPairs = new Map(Array.from(pairs.entries(), ([key, value]) => [key.toLowerCase(), value]));

function preserveWhitespace(original: string, value: string): string {
  const leading = original.match(/^\s*/)?.[0] || "";
  const trailing = original.match(/\s*$/)?.[0] || "";
  return `${leading}${value.trim()}${trailing}`;
}

export function localizeLegacyText(locale: Locale, original: string): string {
  const trimmed = original.trim();
  if (!trimmed) return original;
  for (const [key, value] of Object.entries(messages["en-US"])) {
    const keyOfLocale = key as keyof typeof messages["en-US"];
    if (value === trimmed || messages["zh-CN"][keyOfLocale] === trimmed) return preserveWhitespace(original, messages[locale][keyOfLocale]);
  }
  const pair = pairs.get(trimmed)
    || normalizedPairs.get(trimmed.toLowerCase())
    || Array.from(pairs.values()).find((candidate) => candidate["zh-CN"] === trimmed);
  const translated = pair?.[locale];
  if (translated) return preserveWhitespace(original, translated);
  const dynamicPatterns: Array<[RegExp, (match: RegExpExecArray) => string]> = [
    [/^(\d+) reviewed runs$/, (m) => `${m[1]} ${locale === "zh-CN" ? "条 reviewed Runs" : "reviewed runs"}`],
    [/^(\d+) reviewed version\(s\)$/, (m) => `${m[1]} ${locale === "zh-CN" ? "个 reviewed version(s)" : "reviewed version(s)"}`],
    [/^(\d+) reviewed decisions · decision-only$/, (m) => `${m[1]} ${locale === "zh-CN" ? "个 reviewed Decisions · 仅 Decision" : "reviewed decisions · decision-only"}`],
    [/^(\d+) records$/, (m) => `${m[1]} ${locale === "zh-CN" ? "条记录" : "records"}`],
    [/^(\d+) attempts$/, (m) => `${m[1]} ${locale === "zh-CN" ? "次 Attempts" : "attempts"}`],
    [/^(\d+) events$/, (m) => `${m[1]} ${locale === "zh-CN" ? "个 Events" : "events"}`],
    [/^(\d+) refs$/, (m) => `${m[1]} ${locale === "zh-CN" ? "条 refs" : "refs"}`],
  ];
  for (const [pattern, render] of dynamicPatterns) {
    const match = pattern.exec(trimmed);
    if (match) return preserveWhitespace(original, render(match));
  }
  let fragmentTranslated = original;
  for (const [english, chinese] of FRAGMENT_COPY) {
    fragmentTranslated = locale === "zh-CN"
      ? fragmentTranslated.replaceAll(english, chinese)
      : fragmentTranslated.replaceAll(chinese, english);
  }
  return fragmentTranslated;
}
