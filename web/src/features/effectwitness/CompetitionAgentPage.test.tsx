import { describe, expect, it } from "vitest";
import { agentMode, mayStart, type AgentCapability } from "./competitionAgentApi";

describe("reference Agent admission", () => {
  const fresh: AgentCapability = {
    mode: agentMode, remaining: 1, blocked: false, provider_reservations: 0,
    latest: null, profile: "effectwitness-reference/1", tools: ["refund_order", "apply_config"],
  };
  it("allows only an empty offline Agent owner", () => {
    expect(mayStart(fresh, false)).toBe(true);
    expect(mayStart(null, false)).toBe(false);
    expect(mayStart(fresh, true)).toBe(false);
    expect(mayStart({ ...fresh, mode: "CONTROLLED_LOCAL_PRODUCT" }, false)).toBe(false);
    expect(mayStart({ ...fresh, remaining: 0 }, false)).toBe(false);
    expect(mayStart({ ...fresh, latest: "already-started" }, false)).toBe(false);
    expect(mayStart({ ...fresh, blocked: true }, false)).toBe(false);
    expect(mayStart({ ...fresh, provider_reservations: 1 }, false)).toBe(false);
  });
});
