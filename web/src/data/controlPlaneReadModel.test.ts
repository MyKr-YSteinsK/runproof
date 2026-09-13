import { describe, expect, it } from "vitest";
import type { ControlPlaneMetadataViewDto } from "./controlPlaneReadModel";
import { releaseDecisionListViewModelFromApi } from "./controlPlaneReadModel";
import candidateDecision from "../../../runtime/reviewed-release-decision-candidate.json";

describe("Control Plane API read-model compatibility", () => {
  it("maps an API-style Release Decision summary without exposing persistence fields to presentation", () => {
    const decision = candidateDecision.release_decision;
    const source = decision.source_identity;
    const artifactRef = {
      artifact_id: decision.release_decision_id,
      artifact_key: "release-decision-candidate.json",
      artifact_kind: candidateDecision.artifact_kind,
      schema_version: candidateDecision.schema_version,
      content_sha256: "a".repeat(64),
      source_sha256: source.source_sha256,
      runtime_version: source.runtime_version,
    };
    const dto: ControlPlaneMetadataViewDto = {
      canonical_metadata: {
        entity_type: "RELEASE_DECISION",
        entity_id: decision.release_decision_id,
        outcome: decision.decision_status,
        agent_version: decision.evaluated_agent_version,
        evaluation_id: decision.candidate_evaluation_ref.evaluation_id,
        artifact_ref: artifactRef,
        created_at: decision.decision_timestamp,
      },
      artifact_resolution: { ...artifactRef, resolved: true },
    };
    const viewModel = releaseDecisionListViewModelFromApi(dto);

    expect(viewModel.releaseDecisionId).toBe("release-decision-rpf08-candidate");
    expect(viewModel.decisionStatus).toBe("ELIGIBLE");
    expect(viewModel.evaluatedAgentVersion).toBe("1.0.1-observe-before-mutation-fix");
    expect(viewModel.candidateEvaluationId).toBe("evaluation-29c3943f-84eb-4ce1-a8bc-40321094f31c");
    expect(viewModel.artifact.schemaVersion).toBe("rpf-release-decision-v1");
    expect(viewModel.artifact.sourceSha256).toBe("d6313e5849b2662d9badafa7be25d568e84ab6cc4912c9587495a5f9427bfd69");
    expect(viewModel).not.toHaveProperty("entity_type");
    expect(viewModel).not.toHaveProperty("canonical_metadata");
  });

  it("rejects an API DTO whose resolved artifact identity is inconsistent", () => {
    const decision = candidateDecision.release_decision;
    const artifactRef = {
      artifact_id: decision.release_decision_id,
      artifact_key: "release-decision-candidate.json",
      artifact_kind: candidateDecision.artifact_kind,
      schema_version: candidateDecision.schema_version,
      content_sha256: "a".repeat(64),
      source_sha256: decision.source_identity.source_sha256,
      runtime_version: decision.source_identity.runtime_version,
    };
    const dto: ControlPlaneMetadataViewDto = {
      canonical_metadata: {
        entity_type: "RELEASE_DECISION",
        entity_id: decision.release_decision_id,
        outcome: decision.decision_status,
        agent_version: decision.evaluated_agent_version,
        evaluation_id: decision.candidate_evaluation_ref.evaluation_id,
        artifact_ref: artifactRef,
        created_at: decision.decision_timestamp,
      },
      artifact_resolution: { ...artifactRef, artifact_id: "different-id", resolved: true },
    };
    expect(() => releaseDecisionListViewModelFromApi(dto)).toThrow(/identity-consistent/);
  });
});
