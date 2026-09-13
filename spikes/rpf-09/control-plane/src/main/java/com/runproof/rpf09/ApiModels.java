package com.runproof.rpf09;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

final class ApiModels {

    private ApiModels() {
    }

    record ArtifactRef(
            @JsonProperty("artifact_id") String artifactId,
            @JsonProperty("artifact_key") String artifactKey,
            @JsonProperty("artifact_kind") String artifactKind,
            @JsonProperty("schema_version") String schemaVersion,
            @JsonProperty("content_sha256") String contentSha256,
            @JsonProperty("source_sha256") String sourceSha256,
            @JsonProperty("runtime_version") String runtimeVersion
    ) {
    }

    record IngestManifest(
            @JsonProperty("manifest_schema_version") String manifestSchemaVersion,
            @JsonProperty("entity_type") String entityType,
            @JsonProperty("entity_id") String entityId,
            String outcome,
            @JsonProperty("agent_version") String agentVersion,
            @JsonProperty("evaluation_id") String evaluationId,
            @JsonProperty("idempotency_key") String idempotencyKey,
            @JsonProperty("artifact_ref") ArtifactRef artifactRef
    ) {
    }

    record ArtifactSnapshot(
            @JsonProperty("artifact_id") String artifactId,
            @JsonProperty("artifact_key") String artifactKey,
            @JsonProperty("artifact_kind") String artifactKind,
            @JsonProperty("schema_version") String schemaVersion,
            @JsonProperty("content_sha256") String contentSha256,
            @JsonProperty("source_sha256") String sourceSha256,
            @JsonProperty("runtime_version") String runtimeVersion,
            boolean resolved
    ) {
    }

    record MetadataRecord(
            @JsonProperty("entity_type") String entityType,
            @JsonProperty("entity_id") String entityId,
            String outcome,
            @JsonProperty("agent_version") String agentVersion,
            @JsonProperty("evaluation_id") String evaluationId,
            @JsonProperty("artifact_ref") ArtifactRef artifactRef,
            @JsonProperty("created_at") String createdAt
    ) {
    }

    record MetadataView(
            @JsonProperty("canonical_metadata") MetadataRecord canonicalMetadata,
            @JsonProperty("artifact_resolution") ArtifactSnapshot artifactResolution
    ) {
    }

    record IngestResponse(
            String status,
            @JsonProperty("already_exists") boolean alreadyExists,
            MetadataView metadata
    ) {
    }

    record HealthResponse(
            String status,
            String readiness,
            String database,
            @JsonProperty("schema_version") String schemaVersion
    ) {
    }

    record ApiError(
            String error,
            String message,
            boolean retriable,
            @JsonProperty("evidence_valid") Boolean evidenceValid
    ) {
    }

    record MetadataList(@JsonProperty("items") List<MetadataView> items) {
    }
}
