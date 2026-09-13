package com.runproof.rpf09;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Locale;

import static com.runproof.rpf09.ProbeExceptions.EntityNotFoundException;
import static com.runproof.rpf09.ProbeExceptions.IdentityConflictException;
import static com.runproof.rpf09.ProbeExceptions.RequestValidationException;
import static com.runproof.rpf09.ProbeExceptions.RollbackProbeException;

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
        String entityType = manifest.entityType().toUpperCase(Locale.ROOT);
        artifactRegistry.verify(manifest.artifactRef(), entityType, manifest.entityId());

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
                manifest.artifactRef(),
                Instant.now().toString()
        );
        try {
            jdbcTemplate.update("""
                    INSERT INTO canonical_metadata(
                        entity_type, entity_id, outcome, agent_version, evaluation_id,
                        artifact_id, artifact_key, artifact_kind, artifact_schema_version,
                        artifact_content_sha256, artifact_source_sha256, artifact_runtime_version,
                        idempotency_key, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    metadata.entityType(),
                    metadata.entityId(),
                    metadata.outcome(),
                    metadata.agentVersion(),
                    metadata.evaluationId(),
                    metadata.artifactRef().artifactId(),
                    metadata.artifactRef().artifactKey(),
                    metadata.artifactRef().artifactKind(),
                    metadata.artifactRef().schemaVersion(),
                    metadata.artifactRef().contentSha256(),
                    metadata.artifactRef().sourceSha256(),
                    metadata.artifactRef().runtimeVersion(),
                    manifest.idempotencyKey(),
                    metadata.createdAt()
            );
        } catch (DuplicateKeyException exception) {
            ApiModels.MetadataRecord keyOwner = findByIdempotencyKey(manifest.idempotencyKey());
            if (keyOwner != null && keyOwner.entityType().equals(entityType)
                    && keyOwner.entityId().equals(manifest.entityId())
                    && sameEvidence(keyOwner.artifactRef(), manifest.artifactRef())) {
                return new ApiModels.IngestResponse("IDEMPOTENT_REPLAY", true, view(keyOwner));
            }
            throw new IdentityConflictException("The idempotency key is already bound to another immutable fact.");
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
                SELECT entity_type, entity_id, outcome, agent_version, evaluation_id,
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
                SELECT entity_type, entity_id, outcome, agent_version, evaluation_id,
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
                SELECT entity_type, entity_id, outcome, agent_version, evaluation_id,
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
                new ApiModels.ArtifactRef(
                        rs.getString("artifact_id"),
                        rs.getString("artifact_key"),
                        rs.getString("artifact_kind"),
                        rs.getString("artifact_schema_version"),
                        rs.getString("artifact_content_sha256"),
                        rs.getString("artifact_source_sha256"),
                        rs.getString("artifact_runtime_version")
                ),
                rs.getString("created_at")
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
