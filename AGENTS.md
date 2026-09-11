# AGENTS.md

> 只保存当前仓库独有、执行器无法从通用 Skill 自动知道的事实与硬边界。不要把本文件扩成通用软件工程手册。

## 1. Project identity

- Repository / package: `runproof` / RunProof (`RPF`)
- Primary branch: `main`
- Primary runtime/platform: 尚未建立产品运行时；Primary human surface 为 Desktop Web Control Plane，CLI / Programmatic API / CI 为 automation surfaces
- Key project-state files:
  - `docs/project/PROJECT_BRIEF.md`
  - `docs/project/DECISIONS.md`
  - `docs/project/CURRENT_STATE.md`

## 2. Protected / generated / private boundaries

- Never edit/commit: 用户未授权的无关文件、真实凭据、授权 token、私密数据、真实生产 destructive credentials。
- Generated artifacts: 当前 bootstrap 未定义可提交的生成物；不要提交临时输出、构建产物、覆盖率产物或本地运行目录。
- Secrets/private data: DeepSeek API Key、未来 Provider credentials、authorization token 等不得进入 Git、前端源码、Scenario、默认 Trace 或普通 Evidence export；本地 `.env`、secret 目录与 key 文件由 `.gitignore` 防护。
- Destructive/live/external operations: 不接入真实生产 destructive environment；未经仓库规则或当前明确授权，不执行 deploy、release、publish、真实生产操作，也不创建未知身份的远端仓库。

## 3. Repository command semantics

- Focused test: 当前为文档与仓库 bootstrap；没有产品测试命令。
- Typecheck/lint: 未配置；不得凭空添加脚手架或命令。
- Build: 未配置；当前没有产品构建产物。
- Special validator/compiler: 以 Git 状态、关键文件审查、secret 防护与 Markdown 基础检查作为 bootstrap 验证。
- Browser/PWA check: 不适用；当前未实现 Web/PWA。
- Release verification: 当前无 release/deployment endpoint；只验证本地 Git 事实与交付状态。

## 4. Version / delivery / release model

- Version model: 当前未发布、未建立产品版本号；不要把 bootstrap commit 当成产品版本。
- CHANGELOG model: 当前不创建 CHANGELOG；有真实发布流程后由新 Plan 定义。
- Commit policy: coherent change 在必要验证通过后默认创建 focused commit；本 Plan 完成后提交本轮剩余改动。禁止将无关改动混入提交。
- Push policy: 仅向已明确配置的既定 upstream 做普通 push；当前没有 remote/upstream，不能猜测 owner、name 或 visibility，也不能以未发生的 push 宣称交付完成。
- Publish/release authorization: deploy / release / publish 只有仓库规则或当前明确授权时才可执行；本仓库当前没有此授权。
- Tag/source identity: 当前无 tag、release 或生产 source identity。
- Production endpoint / smoke semantics: 当前不存在；不得伪造部署或 smoke 证据。

## 5. Project-specific invariants

- Evidence first；Observed Fact、Verified Result、Inference、AI Analysis 分层。
- Agent `FAIL` 与 Platform `ERROR` 分离。
- 环境起点不可验证时不得正式 Run；Release Gate 证据不足不得误报可发布。
- `UNKNOWN_OUTCOME` 必须先 reconcile，再决定 retry。
- Failure 经重现、验证与稳定化后才能晋升 Regression。
- Run / Release 历史事实不可静默重写。
- v1 destructive/live side effect 仅允许在 Controlled Production Simulation Environment。
- DeepSeek 是首个 Provider，而不是平台身份。

## 6. Skill routing

- 普通开发 → `frugal-dev-runner`
- UI/移动/浏览器体验 → `ui-real-device-qa`
- PWA/Service Worker/installed-client update/PWA-specific deployment identity → `pwa-release-readiness`
- 普通非 PWA build/deployment identity、release verification → `frugal-dev-runner` + 本 repo 的 release rules
- 工程取证/复盘 → `engineering-retrospective`

正式 Plan / Handoff 与 `TASK_RESULT` 默认使用中文；保留 `TASK_RESULT`、Plan ID、`Status: Complete / Partial / Blocked` 等稳定标识。Optional USER CHECK 只能作为非阻塞建议，不得成为本 Plan 完成前置。

## 7. Repository-specific stop conditions

- 若任务需要未授权的产品取舍、真实生产操作、未知远端身份、凭据或部署权限，停在安全边界并如实报告。
- 不因推荐技术栈一次性创建 React、Spring Boot、Python、PostgreSQL、Queue、容器编排或空洞 CI 骨架。
- 不 force push、擅自 rebase、重写既有 history、覆盖或删除无关用户文件。
