package com.runproof.controlplane;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

import static com.runproof.controlplane.ProbeExceptions.EntityNotFoundException;
import static com.runproof.controlplane.ProbeExceptions.IdentityConflictException;
import static com.runproof.controlplane.ProbeExceptions.InvalidEvidenceException;
import static com.runproof.controlplane.ProbeExceptions.ProbeRollbackException;
import static com.runproof.controlplane.ProbeExceptions.RequestValidationException;

@Service
public class CanonicalMetadataService {

    private static final String MANIFEST_SCHEMA = "rpf-canonical-ingest-v1";
    private static final List<String> DECISION_ROLES = List.of(
            "policy_ref", "suite_ref", "candidate_evaluation_ref", "comparison_ref", "gate_evaluation_ref", "regression_ref"
    );

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;
    private final ArtifactStore artifactStore;

    public CanonicalMetadataService(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper, ArtifactStore artifactStore) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
        this.artifactStore = artifactStore;
    }

    @Transactional
    public ApiModels.IngestResponse ingest(ApiModels.IngestManifest manifest, String principalId, boolean failAfterWrite) {
        NormalizedManifest normalized = validate(manifest, principalId);
        ApiModels.ArtifactSnapshot snapshot = artifactStore.verify(
                normalized.artifactRef(), normalized.entityType(), normalized.entityId()
        );
        JsonNode artifact = artifactStore.readVerified(normalized.artifactRef(), normalized.entityType(), normalized.entityId());
        validateArtifactSemantics(artifact, normalized);
        if ("RELEASE_DECISION".equals(normalized.entityType())) {
            validateDecisionReferences(normalized.keyRefs());
            if (normalized.supersedesEntityId() != null && !normalized.supersedesEntityId().isBlank()
                    && !has("RELEASE_DECISION", normalized.supersedesEntityId())) {
                throw new InvalidEvidenceException("INVALID_DECISION_HISTORY", "Release Decision supersedes an unavailable decision.");
            }
        }

        MetadataRow existing = find(normalized.entityType(), normalized.entityId());
        if (existing != null) {
            return replayOrConflict(existing, normalized);
        }
        MetadataRow idempotencyOwner = findByIdempotency(normalized.idempotencyKey());
        if (idempotencyOwner != null) {
            throw new IdentityConflictException("The idempotency key belongs to a different immutable entity.");
        }

        String summaryJson = json(normalized.summary());
        String refsJson = json(normalized.keyRefs());
        int inserted = jdbcTemplate.update("""
                    INSERT INTO canonical_metadata(
                        entity_type, entity_id, entity_schema_version, artifact_kind, outcome,
                        agent_version, evaluation_id, source_sha256, runtime_version,
                        summary_json, key_refs_json, artifact_id, artifact_key, artifact_schema_version,
                        artifact_content_sha256, artifact_source_sha256, artifact_runtime_version,
                        idempotency_key, supersedes_entity_id, registered_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    normalized.entityType(), normalized.entityId(), normalized.entitySchemaVersion(), normalized.artifactRef().artifactKind(),
                    normalized.outcome(), normalized.agentVersion(), normalized.evaluationId(), normalized.sourceIdentity().sourceSha256(),
                    normalized.sourceIdentity().runtimeVersion(), summaryJson, refsJson,
                    normalized.artifactRef().artifactId(), normalized.artifactRef().artifactKey(), normalized.artifactRef().schemaVersion(),
                    normalized.artifactRef().contentSha256(), normalized.artifactRef().sourceSha256(), normalized.artifactRef().runtimeVersion(),
                    normalized.idempotencyKey(), normalized.supersedesEntityId(), normalized.principalId(), Timestamp.from(Instant.now())
            );
        if (inserted == 0) {
            MetadataRow raced = find(normalized.entityType(), normalized.entityId());
            if (raced != null) return replayOrConflict(raced, normalized);
            MetadataRow owner = findByIdempotency(normalized.idempotencyKey());
            if (owner != null) {
                throw new IdentityConflictException("The idempotency key belongs to a different immutable entity.");
            }
            throw new IllegalStateException("Canonical insert conflicted without a readable owner row.");
        }

        if (failAfterWrite) {
            throw new ProbeRollbackException();
        }
        MetadataRow created = find(normalized.entityType(), normalized.entityId());
        if (created == null) {
            throw new IllegalStateException("Canonical row was not readable after insert.");
        }
        return new ApiModels.IngestResponse("INGESTED", false, toView(created));
    }

    public ApiModels.MetadataView get(String entityType, String entityId) {
        MetadataRow row = find(normalizeEntityType(entityType), entityId);
        if (row == null) throw new EntityNotFoundException("Canonical metadata was not found.");
        return toView(row);
    }

    public ApiModels.MetadataList list(String entityType) {
        String normalized = normalizeEntityType(entityType);
        List<MetadataRow> rows;
        if (normalized == null) {
            rows = jdbcTemplate.query("SELECT * FROM canonical_metadata ORDER BY created_at, entity_type, entity_id", rowMapper());
        } else {
            rows = jdbcTemplate.query(
                    "SELECT * FROM canonical_metadata WHERE entity_type = ? ORDER BY created_at, entity_id",
                    rowMapper(), normalized
            );
        }
        return new ApiModels.MetadataList(rows.stream().map(this::toView).toList());
    }

    public ApiModels.ArtifactResponse readArtifact(String entityType, String entityId) {
        MetadataRow row = find(normalizeEntityType(entityType), entityId);
        if (row == null) throw new EntityNotFoundException("Canonical metadata was not found.");
        ApiModels.ArtifactSnapshot snapshot = artifactStore.verify(row.artifactRef(), row.entityType(), row.entityId());
        return new ApiModels.ArtifactResponse(snapshot, artifactStore.readVerified(row.artifactRef(), row.entityType(), row.entityId()));
    }

    public boolean has(String entityType, String entityId) {
        return find(normalizeEntityType(entityType), entityId) != null;
    }

    private ApiModels.IngestResponse replayOrConflict(MetadataRow existing, NormalizedManifest incoming) {
        if (sameFingerprint(existing, incoming)) {
            return new ApiModels.IngestResponse("IDEMPOTENT_REPLAY", true, toView(existing));
        }
        throw new IdentityConflictException("The immutable entity identity already contains different content.");
    }

    private NormalizedManifest validate(ApiModels.IngestManifest manifest, String principalId) {
        if (manifest == null) throw new RequestValidationException("INVALID_MANIFEST", "Ingest manifest is required.");
        if (!MANIFEST_SCHEMA.equals(manifest.manifestSchemaVersion())) {
            throw new RequestValidationException("UNKNOWN_MANIFEST_SCHEMA", "Manifest schema is not accepted.");
        }
        String entityType = normalizeEntityType(manifest.entityType());
        if (entityType == null || !LocalFileArtifactStore.supports(entityType)) {
            throw new RequestValidationException("UNSUPPORTED_ENTITY_TYPE", "Entity type is not supported.");
        }
        requireText(manifest.entityId(), "entity_id");
        requireText(manifest.entitySchemaVersion(), "entity_schema_version");
        requireText(manifest.outcome(), "outcome");
        requireText(manifest.idempotencyKey(), "idempotency_key");
        if (manifest.entitySchemaVersion() == null || !manifest.entitySchemaVersion().equals(LocalFileArtifactStore.expectedSchema(entityType))) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_UNKNOWN_SCHEMA", "Entity schema does not match its artifact contract.");
        }
        ApiModels.ArtifactRef artifactRef = manifest.artifactRef();
        ApiModels.SourceIdentity source = manifest.sourceIdentity();
        if (source == null) {
            source = new ApiModels.SourceIdentity(artifactRef == null ? null : artifactRef.sourceSha256(), artifactRef == null ? null : artifactRef.runtimeVersion());
        }
        if (artifactRef == null || source.sourceSha256() == null || source.runtimeVersion() == null
                || !Objects.equals(source.sourceSha256(), artifactRef.sourceSha256())
                || !Objects.equals(source.runtimeVersion(), artifactRef.runtimeVersion())) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_SOURCE_IDENTITY", "Manifest source identity does not match its artifact reference.");
        }
        List<ApiModels.EntityRef> keyRefs = manifest.keyRefs() == null ? List.of() : List.copyOf(manifest.keyRefs());
        Map<String, Object> summary = manifest.summary() == null ? Map.of() : Map.copyOf(manifest.summary());
        validateMetadataPayload(summary, keyRefs);
        return new NormalizedManifest(
                entityType, manifest.entityId(), manifest.entitySchemaVersion(), manifest.outcome(), manifest.agentVersion(),
                manifest.evaluationId(), manifest.idempotencyKey(), manifest.supersedesEntityId(), source, keyRefs, summary,
                artifactRef, principalId == null || principalId.isBlank() ? "unknown" : principalId
        );
    }

    private void validateArtifactSemantics(JsonNode artifact, NormalizedManifest manifest) {
        if (!"RELEASE_DECISION".equals(manifest.entityType())) return;
        JsonNode decision = artifact.path("release_decision");
        if (!decision.isObject()) throw new InvalidEvidenceException("INVALID_DECISION_ARTIFACT", "Release Decision artifact is missing its decision object.");
        String status = text(decision, "decision_status");
        if (!List.of("ELIGIBLE", "BLOCKED", "REVIEW_REQUIRED", "INCONCLUSIVE").contains(status)) {
            throw new InvalidEvidenceException("INVALID_DECISION_STATUS", "Release Decision status is not accepted.");
        }
        JsonNode boundary = decision.path("authorization_boundary");
        if (!boundary.isObject() || !Boolean.FALSE.equals(boolOrNull(boundary, "release_executed"))
                || !Boolean.FALSE.equals(boolOrNull(boundary, "deployment_authorized"))) {
            throw new InvalidEvidenceException("INVALID_RELEASE_AUTHORITY_BOUNDARY", "Release Decision is not decision-only.");
        }
        if (!Boolean.TRUE.equals(boolOrNull(decision.path("history"), "immutable"))) {
            throw new InvalidEvidenceException("INVALID_DECISION_HISTORY", "Release Decision history must be immutable.");
        }
    }

    private void validateDecisionReferences(List<ApiModels.EntityRef> refs) {
        Map<String, ApiModels.EntityRef> byRole = new HashMap<>();
        for (ApiModels.EntityRef ref : refs) {
            if (ref != null && ref.role() != null) byRole.put(ref.role(), ref);
        }
        Map<String, String> required = Map.of(
                "policy_ref", "QUALITY_POLICY",
                "suite_ref", "EVALUATION_SUITE",
                "candidate_evaluation_ref", "EVALUATION",
                "comparison_ref", "COMPARISON",
                "gate_evaluation_ref", "QUALITY_GATE",
                "regression_ref", "REGRESSION"
        );
        for (Map.Entry<String, String> requiredRef : required.entrySet()) {
            ApiModels.EntityRef ref = byRole.get(requiredRef.getKey());
            if (ref == null || !requiredRef.getValue().equals(normalizeEntityType(ref.entityType())) || !has(ref.entityType(), ref.entityId())) {
                throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Release Decision references are incomplete or unavailable.");
            }
        }
        if (refs.size() < DECISION_ROLES.size()) {
            throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Release Decision references are incomplete.");
        }
    }

    private void validateMetadataPayload(Map<String, Object> summary, List<ApiModels.EntityRef> refs) {
        try {
            String summaryJson = objectMapper.writeValueAsString(summary);
            String refsJson = objectMapper.writeValueAsString(refs);
            if (summaryJson.length() > 16_384 || refsJson.length() > 16_384) {
                throw new RequestValidationException("CANONICAL_METADATA_TOO_LARGE", "Canonical metadata must remain a bounded summary.");
            }
            String serialized = (summaryJson + refsJson).toLowerCase(Locale.ROOT);
            for (String forbidden : List.of("trajectory", "private_reasoning", "authorization", "bearer ", "password", "deepseek_api_key", "request_messages", "prompt")) {
                if (serialized.contains(forbidden)) {
                    throw new RequestValidationException("CANONICAL_METADATA_SECRET_OR_RAW", "Canonical metadata contains a forbidden raw or secret field.");
                }
            }
        } catch (JsonProcessingException exception) {
            throw new RequestValidationException("INVALID_METADATA_SUMMARY", "Canonical metadata summary is not serializable.");
        }
    }

    private ApiModels.MetadataView toView(MetadataRow row) {
        ApiModels.ArtifactSnapshot resolution;
        try {
            resolution = artifactStore.verify(row.artifactRef(), row.entityType(), row.entityId());
        } catch (InvalidEvidenceException exception) {
            resolution = ApiModels.ArtifactSnapshot.unavailable(row.artifactRef(), exception.code(), row.entityType(), row.entityId());
        }
        return new ApiModels.MetadataView(
                new ApiModels.MetadataRecord(
                        row.entityType(), row.entityId(), row.entitySchemaVersion(), row.artifactKind(), row.outcome(),
                        row.agentVersion(), row.evaluationId(), row.supersedesEntityId(), new ApiModels.SourceIdentity(row.sourceSha256(), row.runtimeVersion()),
                        row.keyRefs(), row.summary(), row.artifactRef(), row.registeredBy(), row.createdAt()
                ),
                resolution
        );
    }

    private MetadataRow find(String entityType, String entityId) {
        if (entityType == null || entityId == null) return null;
        List<MetadataRow> rows = jdbcTemplate.query(
                "SELECT * FROM canonical_metadata WHERE entity_type = ? AND entity_id = ?",
                rowMapper(), entityType, entityId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    private MetadataRow findByIdempotency(String idempotencyKey) {
        List<MetadataRow> rows = jdbcTemplate.query(
                "SELECT * FROM canonical_metadata WHERE idempotency_key = ?",
                rowMapper(), idempotencyKey
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    private RowMapper<MetadataRow> rowMapper() {
        return (rs, rowNum) -> new MetadataRow(
                rs.getString("entity_type"), rs.getString("entity_id"), rs.getString("entity_schema_version"),
                rs.getString("artifact_kind"), rs.getString("outcome"), rs.getString("agent_version"),
                rs.getString("evaluation_id"), rs.getString("supersedes_entity_id"), rs.getString("source_sha256"), rs.getString("runtime_version"),
                readMap(rs.getString("summary_json")),
                readRefs(rs.getString("key_refs_json")),
                new ApiModels.ArtifactRef(
                        rs.getString("artifact_id"), rs.getString("artifact_key"), rs.getString("artifact_kind"),
                        rs.getString("artifact_schema_version"), rs.getString("artifact_content_sha256"),
                        rs.getString("artifact_source_sha256"), rs.getString("artifact_runtime_version")
                ),
                rs.getString("registered_by"), rs.getObject("created_at", java.time.OffsetDateTime.class).toInstant().toString()
        );
    }

    private static boolean sameFingerprint(MetadataRow existing, NormalizedManifest incoming) {
        ApiModels.ArtifactRef old = existing.artifactRef();
        ApiModels.ArtifactRef next = incoming.artifactRef();
        return old.artifactId().equals(next.artifactId())
                && old.artifactKind().equals(next.artifactKind())
                && old.schemaVersion().equals(next.schemaVersion())
                && old.contentSha256().equalsIgnoreCase(next.contentSha256())
                && old.sourceSha256().equalsIgnoreCase(next.sourceSha256())
                && old.runtimeVersion().equals(next.runtimeVersion());
    }

    private static String normalizeEntityType(String value) {
        if (value == null || value.isBlank()) return null;
        return value.trim().toUpperCase(Locale.ROOT);
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) throw new RequestValidationException("INVALID_MANIFEST", "Manifest is missing " + field + ".");
    }

    private static String json(Object value) {
        try {
            return new ObjectMapper().writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new RequestValidationException("INVALID_METADATA_SUMMARY", "Canonical metadata cannot be encoded.");
        }
    }

    private Map<String, Object> readMap(String value) {
        try {
            return objectMapper.readValue(value, new TypeReference<>() {});
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Stored canonical summary is invalid JSON.", exception);
        }
    }

    private List<ApiModels.EntityRef> readRefs(String value) {
        try {
            return objectMapper.readValue(value, new TypeReference<>() {});
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Stored canonical references are invalid JSON.", exception);
        }
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        return value != null && value.isTextual() ? value.asText() : "";
    }

    private static Boolean boolOrNull(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        return value != null && value.isBoolean() ? value.asBoolean() : null;
    }

    private record NormalizedManifest(
            String entityType,
            String entityId,
            String entitySchemaVersion,
            String outcome,
            String agentVersion,
            String evaluationId,
            String idempotencyKey,
            String supersedesEntityId,
            ApiModels.SourceIdentity sourceIdentity,
            List<ApiModels.EntityRef> keyRefs,
            Map<String, Object> summary,
            ApiModels.ArtifactRef artifactRef,
            String principalId
    ) {
    }

    private record MetadataRow(
            String entityType,
            String entityId,
            String entitySchemaVersion,
            String artifactKind,
            String outcome,
            String agentVersion,
            String evaluationId,
            String supersedesEntityId,
            String sourceSha256,
            String runtimeVersion,
            Map<String, Object> summary,
            List<ApiModels.EntityRef> keyRefs,
            ApiModels.ArtifactRef artifactRef,
            String registeredBy,
            String createdAt
    ) {
    }
}
