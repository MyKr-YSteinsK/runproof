import { describe, expect, it } from "vitest";
import { createCanonicalSnapshot } from "../data/canonicalSnapshot";
import { resolveCanonicalRouteState } from "./canonicalRouteState";

describe("resolveCanonicalRouteState", () => {
  const snapshot = createCanonicalSnapshot("fixture");

  it("keeps loading and unavailable distinct", () => {
    expect(resolveCanonicalRouteState("loading", snapshot, {}).kind).toBe("loading");
    expect(resolveCanonicalRouteState("error", snapshot, {}).kind).toBe("unavailable");
  });

  it("resolves a known deep link and distinguishes a missing entity", () => {
    const runId = snapshot.artifacts.allRuns[0].run.runId;
    expect(resolveCanonicalRouteState("ready", snapshot, { runId }).kind).toBe("ready");
    expect(resolveCanonicalRouteState("ready", snapshot, { runId: "run-does-not-exist" }).kind).toBe("not-found");
  });
});
