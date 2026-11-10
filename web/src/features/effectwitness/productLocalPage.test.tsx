import { expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nProvider } from "../../i18n";
import { localEventHref, ProductLocalPage, SessionEvidence, writeBlock } from "./ProductLocalPage";
import { mode, type Capability, type Session } from "./productLocalApi";

it("requires explicit local admission and renders without starting any request", () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  try {
    const markup = renderToStaticMarkup(<I18nProvider><ProductLocalPage search="?event=4" /></I18nProvider>);
    expect(markup).toContain('type="checkbox"');
    expect(markup).toContain('disabled=""');
    expect(markup).toContain("Provider");
    expect(markup).not.toContain("Issuer Signed");
    expect(fetch).not.toHaveBeenCalled();
  } finally { fetch.mockRestore(); }
});

it("fails closed for missing Gateway, pending request, unresolved session and quota", () => {
  const cap: Capability = { mode, blocked: false, remaining: 1, provider_reservations: 0, latest: null };
  expect(writeBlock(cap, undefined, false)).toBeNull();
  expect(writeBlock(null, undefined, false)).toBe("UNAVAILABLE");
  expect(writeBlock(cap, "COMPLETED", true)).toBe("PENDING_REQUEST");
  expect(writeBlock(cap, "RECONCILE_REQUIRED", false)).toBe("RECONCILE_REQUIRED");
  expect(writeBlock({ ...cap, blocked: true }, "COMPLETED", false)).toBe("RECONCILE_REQUIRED");
  expect(writeBlock({ ...cap, remaining: 0 }, "COMPLETED", false)).toBe("NO_QUOTA");
  expect(writeBlock({ ...cap, provider_reservations: 1 }, "COMPLETED", false)).toBe("UNAVAILABLE");
});

it("renders the session facts and preserves event and session query context", () => {
  const feedback = "a".repeat(64);
  const selected = "b".repeat(64);
  const session: Session = {
    session_id: "synthetic/session", status: "RECONCILE_REQUIRED", provider_reservations: 0,
    candidates: [{ candidate: "synthetic-ops", sha256: selected }],
    events: [{ seq: 4, kind: "UNKNOWN", domain: "order" }],
    selection: { decision: "SELECT_OPS", reason: "synthetic", policy_id: "fixture", input_feedback_sha256: feedback,
      selected_candidate_contract_sha256: selected },
    rounds: [{ domain: "order", contract_sha256: "c".repeat(64), tool_status: "UNKNOWN_OUTCOME", authority: "COMMITTED",
      before: { receipts: [] }, after: { receipts: [{}] }, feedback: {}, feedback_sha256: feedback,
      fault: { planned: true, triggered: true, observed: true, agent_exposed: false },
      outcome: { contract_outcome: "CONTRACT_SATISFIED_IN_RUN", verifier_id: "fixture",
        state_diff: { refunded_minor: { before: 0, after: 2500 }, partial: { before: "value" } } } }],
    limits: {}, cleanup: "fixture",
  };
  const search = "?session=synthetic%2Fsession&event=4&from=workbench";
  expect(localEventHref(search, session.session_id, 4)).toBe(`/effectwitness/live-local${search}`);
  const zh = renderToStaticMarkup(<SessionEvidence session={session} search={search} label={(_, text) => text} witness="未取得" />);
  expect(zh).toContain("禁止重放写入");
  expect(zh).toContain("与会话轮次匹配");
  expect(zh).toContain("之前");
  expect(zh).toContain("之后");
  expect(zh).toContain("2500");
  expect(zh).toContain("aria-current=\"step\"");
  expect(zh).toContain("未取得");
  const en = renderToStaticMarkup(<SessionEvidence session={session} search={search} label={text => text} witness="UNAVAILABLE" />);
  expect(en).toContain("Matches session round");
  expect(en).toContain("Write replay prohibited");
  expect(en).toContain("Order tool result");
  expect(en).toContain("Authority readback");
  expect(en).toContain("RULE POLICY");
});
