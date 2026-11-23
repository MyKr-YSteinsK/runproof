# AGENTS.md — RunProof

RunProof is an agent reliability project for verifying tool side effects against controlled business state. The repository is `MyKr-YSteinsK/runproof` and the normal delivery branch is `main`. The portfolio goal and existing reliability contracts are recorded in the project brief.

## Resume work

- Read [PROJECT_BRIEF](docs/project/PROJECT_BRIEF.md) and [CURRENT_STATE](docs/project/CURRENT_STATE.md). Use [DECISIONS](docs/project/DECISIONS.md) for relevant accepted decisions and the [runbook](docs/项目源文件/RUNBOOK.md) for commands and data boundaries.
- Codex can investigate, implement, and verify a direct task. GPT Project Main can plan and review significant work. When an authorized formal handoff uses a GitHub Issue, read its complete body before execution. Use an authorized private source for restricted plans. Keep existing `RPF` identifiers.
- [The upgrade review](docs/项目源文件/UPGRADE_REVIEW.md) is a proposal for the owner's decision. A result, an accepted route, a stage change, and a release require their own evidence or authority.

## Work within the task

- Check the Git root, branch, HEAD, remote, and affected paths before writes. Preserve user changes and stage only task files. Use the existing working tree for routine work. Choose focused tests that exercise the changed behavior and write project-owned temporary outputs under `.local/`.
- Read-only audits, docs, ordinary implementation, and offline tests use normal Git discipline. For new physical owner/database, socket, container/fault or budget experiments, bound the target, resources, output and cleanup. Unknown historical budgets block the affected physical action.
- Explicit authorization is required for paid Provider calls, credentials or permissions changes, external writes, production actions, release/deploy, and contest upload. A normal authorized push to `main` can trigger CI. Check push side effects and verify the remote SHA and resulting runs. Preserve CI failures and required coverage. Confirm scope before a PR, merge, tag or history rewrite.
- `docs/reviews/` is user-protected. Do not enter, enumerate, read, edit, or stage its contents. Keep sealed results, Source Maps, Witness evidence, worktrees, and old `.local/rpf-*` ledgers/WAL/receipts intact. Move verified replaceable items to the task's dated area under `docs/delete/` for user cleanup. The [archive index](docs/history/MAINTENANCE_ARCHIVE.md) locates historical evidence.
- Use a verified executable. On Windows, resolve an installed CPython directly to avoid implicit installation by the Python Install Manager. Never expose Provider keys or user credentials in Git, traces, or logs. Provider-free tasks need no Provider key lookup.

## Reliability contracts

- `UNKNOWN_OUTCOME` requires trusted, deterministic read-only reconciliation before considering another write. A research guard has no real send authority without physical acceptance. RPF-74's native UNKNOWN gap remains a counterexample.
- Keep business truth, deterministic verification, approval, and release authority outside the Agent. `ELIGIBLE` expresses eligibility. Scope authorization for release separately.
- Distinguish `Observed Fact / Verified Result / Inference / AI Analysis` and Agent `PASS/FAIL` from `ERROR/INVALID/INCONCLUSIVE/CANCELLED`. Record fault `planned/triggered/observed/agent_exposed` separately. A hash or self-signed source identity establishes no independent issuer. An offline Witness recheck establishes no new run.
- Record material state in [CURRENT_STATE](docs/project/CURRENT_STATE.md) and approved long-term changes in [DECISIONS](docs/project/DECISIONS.md). Keep proposed changes frozen for review. In delivery report the outcome, branch, full SHA (or `NONE`), checks, CI and outstanding gates.
