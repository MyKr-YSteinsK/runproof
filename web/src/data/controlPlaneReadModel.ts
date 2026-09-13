/**
 * API-shaped DTOs deliberately expose only canonical summary fields and an
 * immutable artifact reference. Presentation code does not depend on SQL
 * column names or on the Control Plane persistence schema.
 */
export interface ControlPlaneArtifactRefDto {
  artifact_id: string;
  artifact_key: string;
  artifact_kind: string;
  schema_version: string;
  content_sha256: string;
  source_sha256: string;
  runtime_version: string;
}

export interface ControlPlaneMetadataDto {
  entity_type: string;
  entity_id: string;
  outcome: string;
  agent_version: string | null;
  evaluation_id: string | null;
  artifact_ref: ControlPlaneArtifactRefDto;
  created_at: string;
}

export interface ControlPlaneMetadataViewDto {
  canonical_metadata: ControlPlaneMetadataDto;
  artifact_resolution: ControlPlaneArtifactRefDto & { resolved: boolean };
}

export interface ReleaseDecisionListViewModel {
  releaseDecisionId: string;
  decisionStatus: string;
  evaluatedAgentVersion: string;
  candidateEvaluationId: string | null;
  createdAt: string;
  artifact: {
    artifactId: string;
    schemaVersion: string;
    contentSha256: string;
    sourceSha256: string;
    runtimeVersion: string;
  };
}

export const releaseDecisionListViewModelFromApi = (
  dto: ControlPlaneMetadataViewDto,
): ReleaseDecisionListViewModel => {
  const metadata = dto.canonical_metadata;
  const resolved = dto.artifact_resolution;
  if (metadata.entity_type !== "RELEASE_DECISION") {
    throw new Error(`Unexpected Control Plane entity type: ${metadata.entity_type}`);
  }
  if (!resolved.resolved || resolved.artifact_id !== metadata.entity_id || resolved.artifact_id !== metadata.artifact_ref.artifact_id) {
    throw new Error("Control Plane artifact reference is not resolved and identity-consistent");
  }
  return {
    releaseDecisionId: metadata.entity_id,
    decisionStatus: metadata.outcome,
    evaluatedAgentVersion: metadata.agent_version || "UNKNOWN",
    candidateEvaluationId: metadata.evaluation_id,
    createdAt: metadata.created_at,
    artifact: {
      artifactId: resolved.artifact_id,
      schemaVersion: resolved.schema_version,
      contentSha256: resolved.content_sha256,
      sourceSha256: resolved.source_sha256,
      runtimeVersion: resolved.runtime_version,
    },
  };
};
