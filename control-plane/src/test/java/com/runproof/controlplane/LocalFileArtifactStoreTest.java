package com.runproof.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LocalFileArtifactStoreTest {

    @TempDir
    Path temp;

    @Test
    void verifiesHashSchemaIdentityAndSourceBeforeReturningArtifact() throws Exception {
        String entityId = "run-test-001";
        String sourceHash = "a".repeat(64);
        byte[] content = new ObjectMapper().writeValueAsBytes(Map.of(
                "artifact_kind", "Run Evidence",
                "schema_version", "rpf-run-evidence-v2",
                "source_sha256", sourceHash,
                "runtime_version", "runtime-test-v1",
                "run", Map.of("run_id", entityId),
                "trajectory", Map.of("events", java.util.List.of())
        ));
        String contentHash = sha256(content);
        String key = "run/" + entityId + "/" + contentHash + ".json";
        Path artifact = temp.resolve(key);
        Files.createDirectories(artifact.getParent());
        Files.write(artifact, content);

        LocalFileArtifactStore store = new LocalFileArtifactStore(new ObjectMapper(), temp.toString());
        ApiModels.ArtifactRef reference = new ApiModels.ArtifactRef(
                entityId, key, "Run Evidence", "rpf-run-evidence-v2", contentHash, sourceHash, "runtime-test-v1"
        );

        ApiModels.ArtifactSnapshot snapshot = store.verify(reference, "RUN", entityId);

        assertTrue(snapshot.resolved());
        assertEquals(contentHash, snapshot.contentSha256());
        assertEquals("/artifacts/RUN/" + entityId, snapshot.artifactUrl());
        assertEquals(entityId, store.readVerified(reference, "RUN", entityId).path("run").path("run_id").asText());
    }

    @Test
    void rejectsTraversalAndHashMismatch() throws Exception {
        LocalFileArtifactStore store = new LocalFileArtifactStore(new ObjectMapper(), temp.toString());
        ApiModels.ArtifactRef traversal = new ApiModels.ArtifactRef(
                "run-test-001", "../outside.json", "Run Evidence", "rpf-run-evidence-v2",
                "0".repeat(64), "a".repeat(64), "runtime-test-v1"
        );

        ProbeExceptions.InvalidEvidenceException pathError = assertThrows(
                ProbeExceptions.InvalidEvidenceException.class,
                () -> store.verify(traversal, "RUN", "run-test-001")
        );
        assertEquals("INVALID_EVIDENCE_ARTIFACT_PATH", pathError.code());

        String existingKey = "run/run-test-001/value.json";
        Path existing = temp.resolve(existingKey);
        Files.createDirectories(existing.getParent());
        Files.writeString(existing, "{}", StandardCharsets.UTF_8);
        ApiModels.ArtifactRef wrongHash = new ApiModels.ArtifactRef(
                "run-test-001", existingKey, "Run Evidence", "rpf-run-evidence-v2",
                "0".repeat(64), "a".repeat(64), "runtime-test-v1"
        );
        ProbeExceptions.InvalidEvidenceException hashError = assertThrows(
                ProbeExceptions.InvalidEvidenceException.class,
                () -> store.verify(wrongHash, "RUN", "run-test-001")
        );
        assertEquals("INVALID_EVIDENCE_ARTIFACT_HASH_MISMATCH", hashError.code());
    }

    @Test
    void rejectsImmutableOverwriteAndAllowsSameBytesReplay() {
        LocalFileArtifactStore store = new LocalFileArtifactStore(new ObjectMapper(), temp.toString());
        String key = "run/run-test-001/immutable.json";
        byte[] original = "original".getBytes(StandardCharsets.UTF_8);

        assertFalse(store.put(key, original).alreadyExists());
        assertTrue(store.put(key, original).alreadyExists());
        ProbeExceptions.InvalidEvidenceException error = assertThrows(
                ProbeExceptions.InvalidEvidenceException.class,
                () -> store.put(key, "changed".getBytes(StandardCharsets.UTF_8))
        );
        assertEquals("ARTIFACT_OVERWRITE_REJECTED", error.code());
    }

    private static String sha256(byte[] content) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
    }
}
