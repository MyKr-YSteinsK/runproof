package com.runproof.controlplane;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.Map;

import static com.runproof.controlplane.ProbeExceptions.InvalidEvidenceException;

/**
 * Provider-neutral artifact contract and byte verification helpers.
 *
 * The canonical metadata service depends on this registry rather than on a
 * concrete filesystem or object-store implementation.  A provider may fetch
 * the bytes differently, but the bytes cross the same verification boundary.
 */
final class ArtifactStoreSupport {

    private static final Map<String, ArtifactContract> CONTRACTS = contracts();

    private ArtifactStoreSupport() {
    }

    static ArtifactContract contract(String entityType) {
        return CONTRACTS.get(entityType);
    }

    static boolean supports(String entityType) {
        return CONTRACTS.containsKey(entityType);
    }

    static String expectedSchema(String entityType) {
        ArtifactContract contract = CONTRACTS.get(entityType);
        return contract == null ? "" : contract.schemaVersion();
    }

    static String expectedKind(String entityType) {
        ArtifactContract contract = CONTRACTS.get(entityType);
        return contract == null ? "" : contract.artifactKind();
    }

    static ArtifactStore.VerifiedArtifact verifyBytes(
            ObjectMapper objectMapper,
            ApiModels.ArtifactRef reference,
            String entityType,
            String entityId,
            byte[] content
    ) {
        ArtifactContract contract = CONTRACTS.get(entityType);
        if (contract == null) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ENTITY_TYPE", "Entity type is not supported.");
        }
        validateReference(reference, entityType, entityId);
        String actualHash = sha256(content);
        if (!actualHash.equalsIgnoreCase(reference.contentSha256())) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_HASH_MISMATCH", "Artifact content hash does not match its reference.");
        }
        JsonNode document = parseObject(objectMapper, content);
        if (!reference.schemaVersion().equals(text(document, "schema_version"))
                || !reference.artifactKind().equals(text(document, "artifact_kind"))) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_IDENTITY", "Artifact header does not match its reference.");
        }
        JsonNode entity = document.path(contract.entityContainer());
        if (!entity.isObject() || !entityId.equals(text(entity, contract.entityIdField()))) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_IDENTITY", "Artifact entity identity does not match its reference.");
        }
        String embeddedSourceHash = findFirstText(document, "source_sha256");
        if (!embeddedSourceHash.isBlank() && !reference.sourceSha256().equalsIgnoreCase(embeddedSourceHash)) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_SOURCE_IDENTITY", "Artifact source identity does not match its reference.");
        }
        String embeddedRuntime = findFirstText(document, "runtime_version");
        if (!embeddedRuntime.isBlank() && !reference.runtimeVersion().equals(embeddedRuntime)) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_SOURCE_IDENTITY", "Artifact runtime identity does not match its reference.");
        }
        ApiModels.ArtifactSnapshot snapshot = new ApiModels.ArtifactSnapshot(
                reference.artifactId(), reference.artifactKey(), reference.artifactKind(), reference.schemaVersion(),
                actualHash, reference.sourceSha256(), reference.runtimeVersion(), true,
                "AVAILABLE", null, artifactUrl(entityType, entityId)
        );
        return new ArtifactStore.VerifiedArtifact(snapshot, document);
    }

    static void validateReference(ApiModels.ArtifactRef reference, String entityType, String entityId) {
        ArtifactContract contract = CONTRACTS.get(entityType);
        if (contract == null) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ENTITY_TYPE", "Entity type is not supported.");
        }
        validateReferenceAgainstContract(reference, entityType, entityId, contract);
    }

    static String validateLogicalKey(String artifactKey) {
        String normalizedKey = artifactKey == null ? "" : artifactKey.replace('\\', '/');
        if (normalizedKey.isBlank() || normalizedKey.startsWith("/") || normalizedKey.startsWith("//")
                || normalizedKey.matches("^[A-Za-z]:/.*")) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact reference must be a relative store key.");
        }
        for (String segment : normalizedKey.split("/", -1)) {
            if (segment.isBlank() || ".".equals(segment) || "..".equals(segment)) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact reference contains an unsafe path segment.");
            }
        }
        return normalizedKey;
    }

    static boolean isSafePathComponent(String value) {
        return value != null && !value.isBlank() && !".".equals(value) && !"..".equals(value)
                && !value.contains("/") && !value.contains("\\") && value.indexOf('\0') < 0;
    }

    static String sha256(byte[] content) {
        try {
            return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
        } catch (Exception exception) {
            throw new IllegalStateException("SHA-256 is unavailable.", exception);
        }
    }

    private static void validateReferenceAgainstContract(ApiModels.ArtifactRef reference, String entityType, String entityId, ArtifactContract contract) {
        if (reference == null) {
            throw new InvalidEvidenceException("INVALID_ARTIFACT_REF", "Artifact reference is required.");
        }
        requireText(reference.artifactId(), "artifact_id");
        requireText(reference.artifactKey(), "artifact_key");
        requireText(reference.artifactKind(), "artifact_kind");
        requireText(reference.schemaVersion(), "schema_version");
        requireText(reference.contentSha256(), "content_sha256");
        requireText(reference.sourceSha256(), "source_sha256");
        requireText(reference.runtimeVersion(), "runtime_version");
        validateLogicalKey(reference.artifactKey());
        if (!isSafePathComponent(entityId) || !isSafePathComponent(reference.artifactId())) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact identity must be a single safe path component.");
        }
        if (!entityId.equals(reference.artifactId())) {
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
    }

    private static JsonNode parseObject(ObjectMapper objectMapper, byte[] content) {
        try {
            JsonNode document = objectMapper.readTree(content);
            if (document == null || !document.isObject()) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_JSON", "Artifact JSON must be an object.");
            }
            return document;
        } catch (JsonProcessingException exception) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_JSON", "Artifact is not valid JSON.");
        } catch (java.io.IOException exception) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_JSON", "Artifact is not valid JSON.");
        }
    }

    private static String artifactUrl(String entityType, String entityId) {
        return "/artifacts/" + entityType + "/" + entityId;
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new InvalidEvidenceException("INVALID_ARTIFACT_REF", "Artifact reference is missing " + field + ".");
        }
    }

    private static boolean isSha256(String value) {
        return value != null && value.matches("[0-9a-fA-F]{64}");
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        return value != null && value.isTextual() ? value.asText() : "";
    }

    private static String findFirstText(JsonNode node, String field) {
        if (node == null) return "";
        if (node.isObject()) {
            String direct = text(node, field);
            if (!direct.isBlank()) return direct;
            var fields = node.fields();
            while (fields.hasNext()) {
                String found = findFirstText(fields.next().getValue(), field);
                if (!found.isBlank()) return found;
            }
        } else if (node.isArray()) {
            for (JsonNode item : node) {
                String found = findFirstText(item, field);
                if (!found.isBlank()) return found;
            }
        }
        return "";
    }

    private static Map<String, ArtifactContract> contracts() {
        Map<String, ArtifactContract> result = new LinkedHashMap<>();
        result.put("RUN", new ArtifactContract("rpf-run-evidence-v2", "Run Evidence", "run", "run_id"));
        result.put("FAILURE_CASE", new ArtifactContract("rpf-failure-case-v1", "Failure Case", "failure_case", "failure_case_id"));
        result.put("REGRESSION", new ArtifactContract("rpf-regression-v1", "Regression", "regression", "regression_id"));
        result.put("REGRESSION_RESULT", new ArtifactContract("rpf-regression-result-v1", "Regression Execution Result", "result", "result_id"));
        result.put("REGRESSION_COLLECTION", new ArtifactContract("rpf-regression-collection-v1", "Historical Regression Collection", "collection", "collection_id"));
        result.put("PROMOTION_GATE", new ArtifactContract("rpf-promotion-gate-v1", "Promotion Gate Evaluation", "gate", "gate_id"));
        result.put("EVALUATION_SUITE", new ArtifactContract("rpf-evaluation-suite-v1", "Evaluation Suite", "suite", "suite_id"));
        result.put("EVALUATION", new ArtifactContract("rpf-evaluation-result-v1", "Evaluation Result", "evaluation", "evaluation_id"));
        result.put("COMPARISON", new ArtifactContract("rpf-evaluation-comparison-v1", "Evaluation Comparison", "comparison", "comparison_id"));
        result.put("QUALITY_POLICY", new ArtifactContract("rpf-quality-policy-v1", "Quality Policy", "policy", "policy_id"));
        result.put("QUALITY_GATE", new ArtifactContract("rpf-quality-gate-evaluation-v1", "Quality Gate Evaluation", "gate_evaluation", "gate_evaluation_id"));
        result.put("RELEASE_DECISION", new ArtifactContract("rpf-release-decision-v1", "Release Decision", "release_decision", "release_decision_id"));
        result.put("FAILURE_INTELLIGENCE", new ArtifactContract("rpf-failure-intelligence-v1", "Failure Intelligence", "intelligence", "intelligence_id"));
        result.put("FAILURE_CLUSTER", new ArtifactContract("rpf-failure-cluster-v1", "Failure Cluster", "cluster", "cluster_id"));
        result.put("VERSION_BISECT", new ArtifactContract("rpf-version-bisect-v1", "Version Bisect", "bisect", "bisect_id"));
        result.put("STATISTICAL_SAMPLING_PLAN", new ArtifactContract("rpf-statistical-sampling-plan-v1", "Statistical Sampling Plan", "sampling_plan", "sampling_plan_id"));
        result.put("STATISTICAL_EVALUATION", new ArtifactContract("rpf-statistical-evaluation-v1", "Statistical Evaluation", "statistical_evaluation", "evaluation_id"));
        result.put("STATISTICAL_COMPARISON", new ArtifactContract("rpf-statistical-comparison-v1", "Statistical Comparison", "statistical_comparison", "comparison_id"));
        result.put("STATISTICAL_POLICY", new ArtifactContract("rpf-statistical-policy-v1", "Statistical Policy", "statistical_policy", "policy_id"));
        result.put("STATISTICAL_GATE", new ArtifactContract("rpf-statistical-quality-gate-v1", "Statistical Quality Gate", "statistical_gate", "gate_evaluation_id"));
        result.put("STATISTICAL_RELEASE_DECISION", new ArtifactContract("rpf-statistical-release-decision-v1", "Statistical Release Decision", "statistical_release_decision", "release_decision_id"));
        return Map.copyOf(result);
    }

    record ArtifactContract(String schemaVersion, String artifactKind, String entityContainer, String entityIdField) {
    }
}
