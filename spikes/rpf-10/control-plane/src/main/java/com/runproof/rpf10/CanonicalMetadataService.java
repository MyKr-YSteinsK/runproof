package com.runproof.rpf10;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Locale;

import static com.runproof.rpf10.ProbeExceptions.EntityNotFoundException;
import static com.runproof.rpf10.ProbeExceptions.IdentityConflictException;
import static com.runproof.rpf10.ProbeExceptions.InvalidEvidenceException;
import static com.runproof.rpf10.ProbeExceptions.RequestValidationException;
import static com.runproof.rpf10.ProbeExceptions.RollbackProbeException;

/**
 * Owns canonical, queryable metadata only. The referenced artifact remains in
 * the immutable local store and is revalidated on every read.
 */
@Service
public class CanonicalMetadataService {

    public static final String MANIFEST_SCHEMA_VERSION = "rpf-control-plane-ingest-v1";

    private final JdbcTemplate jdbcTemplate;
    private final ArtifactRegistry artifactRegistry;

    public CanonicalMetadataService(JdbcTemplate jdbcTemplate, ArtifactRegistry artifactRegistry) {
        this.jdbcTemplate = jdbcTemplate;
        this.artifactRegistry = artifactRegistry;
    }

    @Transactional
    public ApiModels.IngestResponse ingest(ApiModels.IngestManifest manifest, boolean failAfterWrite) {
        validateManifest(manifest);
        String entityType = normalizeEntityType(manifest.entityType());
        artifactRegistry.verify(manifest.artifactRef(), entityType, manifest.entityId());
        validateDecisionRelationships(manifest, entityType);

        ApiModels.MetadataRecord existing = find(entityType, manifest.entityId());
        if (existing != null) {
            if (sameEvidence(existing.artifactRef(), manifest.artifactRef())) {
                return new ApiModels.IngestResponse("IDEMPOTENT_REPLAY", true, view(existing));
            }
            throw new IdentityConflictException("The entity identity already points to different content.");
        }

        ApiModels.MetadataRecord metadata = new ApiModels.MetadataRecord(
                entityType,
                manifest.entityId(),
                manifest.outcome(),
                manifest.agentVersion(),
                manifest.evaluationId(),
                manifest.supersedesDecisionId(),
                manifest.artifactRef(),
                Instant.now().toString()
        );

        // PostgreSQL aborts a transaction after a duplicate-key exception. An
        // INSERT ... ON CONFLICT DO NOTHING lets the race be reconciled in the
        // same transaction, preserving idempotency without a rollback/retry
        // side channel.
        int inserted = jdbcTemplate.update("""
                INSERT INTO canonical_metadata(
                    entity_type, entity_id, outcome, agent_version, evaluation_id, supersedes_decision_id,
                    artifact_id, artifact_key, artifact_kind, artifact_schema_version,
                    artifact_content_sha256, artifact_source_sha256, artifact_runtime_version,
                    idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                metadata.entityType(),
                metadata.entityId(),
                metadata.outcome(),
                metadata.agentVersion(),
                metadata.evaluationId(),
                metadata.supersedesDecisionId(),
                metadata.artifactRef().artifactId(),
                metadata.artifactRef().artifactKey(),
                metadata.artifactRef().artifactKind(),
                metadata.artifactRef().schemaVersion(),
                metadata.artifactRef().contentSha256(),
                metadata.artifactRef().sourceSha256(),
                metadata.artifactRef().runtimeVersion(),
                manifest.idempotencyKey(),
                Timestamp.from(Instant.parse(metadata.createdAt())
                )
        );

        if (inserted == 0) {
            ApiModels.MetadataRecord identityOwner = find(entityType, manifest.entityId());
            if (identityOwner != null && sameEvidence(identityOwner.artifactRef(), manifest.artifactRef())) {
                return new ApiModels.IngestResponse("IDEMPOTENT_REPLAY", true, view(identityOwner));
            }
            ApiModels.MetadataRecord keyOwner = findByIdempotencyKey(manifest.idempotencyKey());
            if (keyOwner != null && keyOwner.entityType().equals(entityType)
                    && keyOwner.entityId().equals(manifest.entityId())
                    && sameEvidence(keyOwner.artifactRef(), manifest.artifactRef())) {
                return new ApiModels.IngestResponse("IDEMPOTENT_REPLAY", true, view(keyOwner));
            }
            throw new IdentityConflictException("The immutable identity or idempotency key is already bound to different content.");
        }

        if (failAfterWrite) {
            throw new RollbackProbeException();
        }
        return new ApiModels.IngestResponse("INGESTED", false, view(metadata));
    }

    public ApiModels.MetadataView get(String entityType, String entityId) {
        String normalizedType = normalizeEntityType(entityType);
        ApiModels.MetadataRecord metadata = find(normalizedType, entityId);
        if (metadata == null) {
            throw new EntityNotFoundException("No canonical metadata exists for this identity.");
        }
        return view(metadata);
    }

    public ApiModels.MetadataList list(String entityType) {
        String normalizedType = normalizeEntityType(entityType);
        List<ApiModels.MetadataRecord> records = jdbcTemplate.query(
                """
                SELECT entity_type, entity_id, outcome, agent_version, evaluation_id, supersedes_decision_id,
                       artifact_id, artifact_key, artifact_kind, artifact_schema_version,
                       artifact_content_sha256, artifact_source_sha256, artifact_runtime_version,
                       created_at
                FROM canonical_metadata
                WHERE entity_type = ?
                ORDER BY created_at, entity_id
                """,
                (rs, rowNum) -> fromRow(rs),
                normalizedType
        );
        return new ApiModels.MetadataList(records.stream().map(this::view).toList());
    }

    private void validateDecisionRelationships(ApiModels.IngestManifest manifest, String entityType) {
        if (!"RELEASE_DECISION".equals(entityType)) {
            if (manifest.supersedesDecisionId() != null && !manifest.supersedesDecisionId().isBlank()) {
                throw new RequestValidationException("INVALID_SUPERSEDES_REFERENCE", "Only Release Decision manifests may supersede a decision.");
            }
            return;
        }
        if (manifest.evaluationId() == null || manifest.evaluationId().isBlank()) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_RELATIONSHIP", "Release Decision must reference an Evaluation.");
        }
        if (find("EVALUATION", manifest.evaluationId()) == null) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_RELATIONSHIP", "Release Decision references unknown Evaluation evidence.");
        }
        if (manifest.supersedesDecisionId() != null && !manifest.supersedesDecisionId().isBlank()
                && find("RELEASE_DECISION", manifest.supersedesDecisionId()) == null) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_RELATIONSHIP", "Release Decision supersedes an unknown decision.");
        }
    }

    private ApiModels.MetadataView view(ApiModels.MetadataRecord metadata) {
        ApiModels.ArtifactSnapshot resolved = artifactRegistry.verify(
                metadata.artifactRef(), metadata.entityType(), metadata.entityId()
        );
        return new ApiModels.MetadataView(metadata, resolved);
    }

    private ApiModels.MetadataRecord find(String entityType, String entityId) {
        if (entityId == null || entityId.isBlank()) {
            throw new RequestValidationException("INVALID_ENTITY_ID", "Entity id is required.");
        }
        List<ApiModels.MetadataRecord> records = jdbcTemplate.query(
                """
                SELECT entity_type, entity_id, outcome, agent_version, evaluation_id, supersedes_decision_id,
                       artifact_id, artifact_key, artifact_kind, artifact_schema_version,
                       artifact_content_sha256, artifact_source_sha256, artifact_runtime_version,
                       created_at
                FROM canonical_metadata
                WHERE entity_type = ? AND entity_id = ?
                """,
                (rs, rowNum) -> fromRow(rs),
                entityType,
                entityId
        );
        return records.isEmpty() ? null : records.get(0);
    }

    private ApiModels.MetadataRecord findByIdempotencyKey(String idempotencyKey) {
        List<ApiModels.MetadataRecord> records = jdbcTemplate.query(
                """
                SELECT entity_type, entity_id, outcome, agent_version, evaluation_id, supersedes_decision_id,
                       artifact_id, artifact_key, artifact_kind, artifact_schema_version,
                       artifact_content_sha256, artifact_source_sha256, artifact_runtime_version,
                       created_at
                FROM canonical_metadata
                WHERE idempotency_key = ?
                """,
                (rs, rowNum) -> fromRow(rs),
                idempotencyKey
        );
        return records.isEmpty() ? null : records.get(0);
    }

    private ApiModels.MetadataRecord fromRow(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new ApiModels.MetadataRecord(
                rs.getString("entity_type"),
                rs.getString("entity_id"),
                rs.getString("outcome"),
                rs.getString("agent_version"),
                rs.getString("evaluation_id"),
                rs.getString("supersedes_decision_id"),
                new ApiModels.ArtifactRef(
                        rs.getString("artifact_id"),
                        rs.getString("artifact_key"),
                        rs.getString("artifact_kind"),
                        rs.getString("artifact_schema_version"),
                        rs.getString("artifact_content_sha256"),
                        rs.getString("artifact_source_sha256"),
                        rs.getString("artifact_runtime_version")
                ),
                rs.getTimestamp("created_at").toInstant().toString()
        );
    }

    private static boolean sameEvidence(ApiModels.ArtifactRef left, ApiModels.ArtifactRef right) {
        return left.artifactId().equals(right.artifactId())
                && left.artifactKind().equals(right.artifactKind())
                && left.schemaVersion().equals(right.schemaVersion())
                && left.contentSha256().equalsIgnoreCase(right.contentSha256())
                && left.sourceSha256().equalsIgnoreCase(right.sourceSha256())
                && left.runtimeVersion().equals(right.runtimeVersion());
    }

    private static String normalizeEntityType(String entityType) {
        if (entityType == null || entityType.isBlank()) {
            throw new RequestValidationException("INVALID_ENTITY_TYPE", "Entity type is required.");
        }
        String normalized = entityType.toUpperCase(Locale.ROOT);
        if (!normalized.equals("RUN") && !normalized.equals("EVALUATION") && !normalized.equals("RELEASE_DECISION")) {
            throw new RequestValidationException("INVALID_ENTITY_TYPE", "Entity type is not supported by this probe.");
        }
        return normalized;
    }

    private static void validateManifest(ApiModels.IngestManifest manifest) {
        if (manifest == null) {
            throw new RequestValidationException("INVALID_MANIFEST", "Ingest manifest is required.");
        }
        if (!MANIFEST_SCHEMA_VERSION.equals(manifest.manifestSchemaVersion())) {
            throw new RequestValidationException("UNKNOWN_MANIFEST_SCHEMA", "Ingest manifest schema is not accepted.");
        }
        normalizeEntityType(manifest.entityType());
        requireText(manifest.entityId(), "INVALID_ENTITY_ID", "entity_id");
        requireText(manifest.outcome(), "INVALID_OUTCOME", "outcome");
        requireText(manifest.idempotencyKey(), "INVALID_IDEMPOTENCY_KEY", "idempotency_key");
        if (manifest.artifactRef() == null) {
            throw new RequestValidationException("INVALID_ARTIFACT_REF", "artifact_ref is required.");
        }
    }

    private static void requireText(String value, String code, String field) {
        if (value == null || value.isBlank()) {
            throw new RequestValidationException(code, field + " is required.");
        }
    }
}
