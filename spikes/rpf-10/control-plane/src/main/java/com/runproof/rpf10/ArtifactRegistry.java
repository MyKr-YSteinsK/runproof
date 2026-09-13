package com.runproof.rpf10;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Map;

import static com.runproof.rpf10.ProbeExceptions.InvalidEvidenceException;

/**
 * Reference-only artifact registry for the probe. It never stores raw
 * artifacts in canonical metadata and rejects path traversal/symlink escapes.
 */
@Component
public class ArtifactRegistry {

    private static final Map<String, ArtifactContract> CONTRACTS = Map.of(
            "RUN", new ArtifactContract("rpf-run-evidence-v2", "Run Evidence", "run", "run_id", "runtime"),
            "EVALUATION", new ArtifactContract("rpf-evaluation-result-v1", "Evaluation Result", "evaluation", "evaluation_id", "runtime"),
            "RELEASE_DECISION", new ArtifactContract("rpf-release-decision-v1", "Release Decision", "release_decision", "release_decision_id", "source_identity")
    );

    private final ObjectMapper objectMapper;
    private final Path artifactRoot;

    public ArtifactRegistry(
            ObjectMapper objectMapper,
            @Value("${rpf.artifact-dir:.local/rpf-10/artifacts}") String configuredRoot
    ) {
        this.objectMapper = objectMapper;
        this.artifactRoot = Path.of(configuredRoot).toAbsolutePath().normalize();
        try {
            Files.createDirectories(this.artifactRoot);
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot create artifact store", exception);
        }
    }

    public ApiModels.ArtifactSnapshot verify(
            ApiModels.ArtifactRef reference,
            String entityType,
            String entityId
    ) {
        ArtifactContract contract = CONTRACTS.get(entityType);
        if (contract == null) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ENTITY_TYPE", "Unsupported entity type.");
        }
        if (reference == null) {
            throw new InvalidEvidenceException("INVALID_ARTIFACT_REF", "Artifact reference is required.");
        }
        requireText(reference.artifactId(), "INVALID_ARTIFACT_REF", "artifact_id");
        requireText(reference.artifactKey(), "INVALID_ARTIFACT_REF", "artifact_key");
        requireText(reference.artifactKind(), "INVALID_ARTIFACT_REF", "artifact_kind");
        requireText(reference.schemaVersion(), "INVALID_ARTIFACT_REF", "schema_version");
        requireText(reference.contentSha256(), "INVALID_ARTIFACT_REF", "content_sha256");
        requireText(reference.sourceSha256(), "INVALID_ARTIFACT_REF", "source_sha256");
        requireText(reference.runtimeVersion(), "INVALID_ARTIFACT_REF", "runtime_version");

        if (!reference.artifactId().equals(entityId)) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_IDENTITY", "Artifact id does not match entity id.");
        }
        if (!contract.schemaVersion().equals(reference.schemaVersion())) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_UNKNOWN_SCHEMA", "Artifact schema is not accepted for this entity type.");
        }
        if (!contract.artifactKind().equals(reference.artifactKind())) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_KIND", "Artifact kind does not match entity type.");
        }
        if (!isSha256(reference.contentSha256()) || !isSha256(reference.sourceSha256())) {
            throw new InvalidEvidenceException("INVALID_ARTIFACT_REF", "Artifact hashes must be SHA-256 values.");
        }

        Path resolved = resolveInsideStore(reference.artifactKey());
        if (!Files.isRegularFile(resolved)) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_MISSING", "Referenced artifact is missing.");
        }
        try {
            Path realPath = resolved.toRealPath();
            Path realRoot = artifactRoot.toRealPath();
            if (!realPath.startsWith(realRoot)) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact reference escapes the artifact store.");
            }
            byte[] content = Files.readAllBytes(realPath);
            String actualHash = sha256(content);
            if (!actualHash.equalsIgnoreCase(reference.contentSha256())) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_HASH_MISMATCH", "Artifact content hash does not match its reference.");
            }
            JsonNode document;
            try {
                document = objectMapper.readTree(content);
            } catch (JsonProcessingException exception) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_JSON", "Artifact is not valid JSON.");
            }
            if (document == null || !document.isObject()) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_JSON", "Artifact JSON must be an object.");
            }
            if (!reference.schemaVersion().equals(text(document, "schema_version"))
                    || !reference.artifactKind().equals(text(document, "artifact_kind"))) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_IDENTITY", "Artifact header does not match its reference.");
            }
            JsonNode entity = document.path(contract.entityContainer());
            if (!entity.isObject() || !entityId.equals(text(entity, contract.entityIdField()))) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_IDENTITY", "Artifact entity identity does not match its reference.");
            }
            JsonNode source = entity.path(contract.sourceContainer());
            String sourceHash = text(source, "source_sha256");
            String runtimeVersion = text(source, "runtime_version");
            if (!reference.sourceSha256().equalsIgnoreCase(sourceHash)
                    || !reference.runtimeVersion().equals(runtimeVersion)) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_SOURCE_IDENTITY", "Artifact source identity does not match its reference.");
            }
            return new ApiModels.ArtifactSnapshot(
                    reference.artifactId(),
                    reference.artifactKey(),
                    reference.artifactKind(),
                    reference.schemaVersion(),
                    actualHash,
                    sourceHash,
                    runtimeVersion,
                    true
            );
        } catch (IOException exception) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_READ", "Artifact could not be read.");
        }
    }

    private Path resolveInsideStore(String artifactKey) {
        String normalizedKey = artifactKey.replace('\\', '/');
        if (normalizedKey.startsWith("/") || normalizedKey.matches("^[A-Za-z]:/.*")
                || normalizedKey.lines().anyMatch(line -> line.contains(".."))) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact reference must be a relative store key.");
        }
        Path resolved = artifactRoot.resolve(normalizedKey).normalize();
        if (!resolved.startsWith(artifactRoot)) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact reference escapes the artifact store.");
        }
        return resolved;
    }

    private static void requireText(String value, String code, String field) {
        if (value == null || value.isBlank()) {
            throw new InvalidEvidenceException(code, "Artifact reference is missing " + field + ".");
        }
    }

    private static boolean isSha256(String value) {
        return value != null && value.matches("[0-9a-fA-F]{64}");
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        return value != null && value.isTextual() ? value.asText() : "";
    }

    private static String sha256(byte[] content) {
        try {
            return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
        } catch (Exception exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    private record ArtifactContract(
            String schemaVersion,
            String artifactKind,
            String entityContainer,
            String entityIdField,
            String sourceContainer
    ) {
    }
}
