import { describe, expect, it } from "vitest";
import { goldenDemoArtifact, goldenDemoProfile, goldenDemoRefId } from "./goldenDemo";

describe("Golden Demo contract", () => {
  it("declares two explicit agents and a versioned source", () => {
    expect(goldenDemoProfile.schema_version).toBe("rpf-golden-demo-profile-v1");
    expect(goldenDemoProfile.demo.demo_id).toBe("runproof-golden-demo");
    expect(goldenDemoProfile.agents.map((agent) => agent.agent_id)).toEqual([
      "production-change-agent",
      "incident-remediation-agent",
    ]);
    expect(goldenDemoProfile.demo.no_provider_required).toBe(true);
  });

  it("covers every Golden Demo investigation boundary with reviewed refs", () => {
    expect(goldenDemoProfile.reviewed_artifacts).toHaveLength(15);
    for (const role of [
      "statistical.stable",
      "statistical.flaky",
      "statistical.safety",
      "statistical.evidence_poor",
      "failure.flagship_cluster",
      "version.bisect",
      "release.decision",
      "durable.response_lost_run",
    ]) {
      expect(goldenDemoArtifact(role).content_sha256).toMatch(/^[0-9a-f]{64}$/);
    }
  });

  it("keeps selected refs stable and decision-only", () => {
    expect(goldenDemoRefId("release.decision")).toBe("release-decision-rpf16-reviewed-candidate");
    expect(goldenDemoProfile.selected.statistical_evaluations).toContain("statistical-evaluation-rpf18-safety");
    expect(goldenDemoProfile.demo.no_release_or_deploy).toBe(true);
  });
});
