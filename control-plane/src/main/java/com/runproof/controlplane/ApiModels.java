package com.runproof.controlplane;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.List;
import java.util.Map;

final class ApiModels {

    private ApiModels() {
    }

    record SourceIdentity(
            @JsonProperty("source_sha256") String sourceSha256,
            @JsonProperty("runtime_version") String runtimeVersion
    ) {
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

    record EntityRef(
            @JsonProperty("entity_type") String entityType,
            @JsonProperty("entity_id") String entityId,
            String role
    ) {
    }

    record IngestManifest(
            @JsonProperty("manifest_schema_version") String manifestSchemaVersion,
            @JsonProperty("entity_type") String entityType,
            @JsonProperty("entity_id") String entityId,
            @JsonProperty("entity_schema_version") String entitySchemaVersion,
            String outcome,
            @JsonProperty("agent_version") String agentVersion,
            @JsonProperty("evaluation_id") String evaluationId,
            @JsonProperty("idempotency_key") String idempotencyKey,
            @JsonProperty("supersedes_entity_id") String supersedesEntityId,
            @JsonProperty("source_identity") SourceIdentity sourceIdentity,
            @JsonProperty("key_refs") List<EntityRef> keyRefs,
            Map<String, Object> summary,
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
            boolean resolved,
            String availability,
            @JsonProperty("error_code") String errorCode,
            @JsonProperty("artifact_url") String artifactUrl
    ) {
        static ArtifactSnapshot resolved(ArtifactRef ref, String entityType, String entityId) {
            return new ArtifactSnapshot(
                    ref.artifactId(), ref.artifactKey(), ref.artifactKind(), ref.schemaVersion(),
                    ref.contentSha256(), ref.sourceSha256(), ref.runtimeVersion(), true,
                    "AVAILABLE", null, "/artifacts/" + entityType + "/" + entityId
            );
        }

        static ArtifactSnapshot unavailable(ArtifactRef ref, String code, String entityType, String entityId) {
            return new ArtifactSnapshot(
                    ref.artifactId(), ref.artifactKey(), ref.artifactKind(), ref.schemaVersion(),
                    ref.contentSha256(), ref.sourceSha256(), ref.runtimeVersion(), false,
                    "UNAVAILABLE_OR_INVALID", code, "/artifacts/" + entityType + "/" + entityId
            );
        }
    }

    record MetadataRecord(
            @JsonProperty("entity_type") String entityType,
            @JsonProperty("entity_id") String entityId,
            @JsonProperty("entity_schema_version") String entitySchemaVersion,
            @JsonProperty("artifact_kind") String artifactKind,
            String outcome,
            @JsonProperty("agent_version") String agentVersion,
            @JsonProperty("evaluation_id") String evaluationId,
            @JsonProperty("supersedes_entity_id") String supersedesEntityId,
            @JsonProperty("source_identity") SourceIdentity sourceIdentity,
            @JsonProperty("key_refs") List<EntityRef> keyRefs,
            Map<String, Object> summary,
            @JsonProperty("artifact_ref") ArtifactRef artifactRef,
            @JsonProperty("registered_by") String registeredBy,
            @JsonProperty("created_at") String createdAt
    ) {
    }

    record MetadataView(
            @JsonProperty("canonical_metadata") MetadataRecord canonicalMetadata,
            @JsonProperty("artifact_resolution") ArtifactSnapshot artifactResolution
    ) {
    }

    record MetadataList(List<MetadataView> items) {
    }

    record IngestResponse(
            String status,
            @JsonProperty("already_exists") boolean alreadyExists,
            MetadataView metadata
    ) {
    }

    record ArtifactResponse(
            @JsonProperty("artifact_ref") ArtifactSnapshot artifactRef,
            JsonNode artifact
    ) {
    }

    record HealthResponse(
            String process,
            String database,
            String migration,
            @JsonProperty("artifact_store") String artifactStore,
            String readiness,
            boolean ready,
            @JsonProperty("schema_version") String schemaVersion,
            @JsonProperty("database_product") String databaseProduct,
            @JsonProperty("database_version") String databaseVersion,
            @JsonProperty("jdbc_driver") String jdbcDriver,
            @JsonProperty("jdbc_driver_version") String jdbcDriverVersion,
            @JsonProperty("database_name") String databaseName,
            @JsonProperty("database_schema") String databaseSchema
    ) {
    }

    record ApiError(
            String error,
            String message,
            boolean retriable,
            @JsonProperty("evidence_valid") Boolean evidenceValid,
            @JsonProperty("correlation_id") String correlationId
    ) {
    }

    record Boundary(
            String transport,
            @JsonProperty("canonical_store") String canonicalStore,
            @JsonProperty("artifact_store") String artifactStore,
            @JsonProperty("authentication") String authentication,
            @JsonProperty("active_scopes") List<String> activeScopes,
            @JsonProperty("agent_has_release_decision_authority") boolean agentHasReleaseDecisionAuthority,
            @JsonProperty("evidence_writer_has_release_decision_authority") boolean evidenceWriterHasReleaseDecisionAuthority,
            @JsonProperty("release_or_deploy_authorized") boolean releaseOrDeployAuthorized,
            @JsonProperty("approval_authority_implemented") boolean approvalAuthorityImplemented,
            @JsonProperty("queue_or_broker") boolean queueOrBroker,
            @JsonProperty("job_transport_resolved") boolean jobTransportResolved,
            @JsonProperty("ci_integration") String ciIntegration
    ) {
    }

    record AuditEvent(
            @JsonProperty("audit_id") long auditId,
            @JsonProperty("principal_id") String principalId,
            String action,
            @JsonProperty("entity_type") String entityType,
            @JsonProperty("entity_id") String entityId,
            String result,
            @JsonProperty("request_id") String requestId,
            @JsonProperty("reason_code") String reasonCode,
            @JsonProperty("occurred_at") String occurredAt
    ) {
    }

    record AuditList(List<AuditEvent> items) {
    }
}
