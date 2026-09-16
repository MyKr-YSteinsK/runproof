package com.runproof.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

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
        ArtifactStore.VerifiedArtifact verified = store.readVerifiedArtifact(reference, "RUN", entityId);

        assertTrue(snapshot.resolved());
        assertEquals(contentHash, snapshot.contentSha256());
        assertEquals("/artifacts/RUN/" + entityId, snapshot.artifactUrl());
        assertEquals(contentHash, verified.snapshot().contentSha256());
        assertEquals(entityId, verified.document().path("run").path("run_id").asText());
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

    @Test
    void rejectsParentSymlinkEscapeBeforeCreatingArtifact() throws Exception {
        Path root = temp.resolve("store");
        Path outside = temp.resolve("outside");
        Files.createDirectories(root);
        Files.createDirectories(outside);
        Path escapeLink = root.resolve("run");
        Assumptions.assumeTrue(createDirectoryEscapeLink(escapeLink, outside),
                "The current Windows filesystem does not permit symbolic-link or junction construction for this test.");

        try {
            LocalFileArtifactStore store = new LocalFileArtifactStore(new ObjectMapper(), root.toString());
            ProbeExceptions.InvalidEvidenceException error = assertThrows(
                    ProbeExceptions.InvalidEvidenceException.class,
                    () -> store.put("run/escape.json", "escaped".getBytes(StandardCharsets.UTF_8))
            );

            assertEquals("INVALID_EVIDENCE_ARTIFACT_PATH", error.code());
            assertFalse(Files.exists(outside.resolve("escape.json")));
        } finally {
            Files.deleteIfExists(escapeLink);
        }
    }

    private static boolean createDirectoryEscapeLink(Path link, Path target) throws Exception {
        try {
            Files.createSymbolicLink(link, target);
            return true;
        } catch (UnsupportedOperationException | java.io.IOException ignored) {
            Process process = new ProcessBuilder(
                    "cmd.exe", "/c", "mklink /J \"" + link + "\" \"" + target + "\"")
                    .redirectErrorStream(true)
                    .start();
            int exitCode = process.waitFor();
            return exitCode == 0 && Files.isDirectory(link);
        }
    }

    @Test
    void verifiedReadReturnsTheBytesThatWereValidated() throws Exception {
        String entityId = "run-mutation-001";
        String sourceHash = "b".repeat(64);
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
        ApiModels.ArtifactRef reference = new ApiModels.ArtifactRef(
                entityId, key, "Run Evidence", "rpf-run-evidence-v2", contentHash, sourceHash, "runtime-test-v1"
        );
        AtomicInteger reads = new AtomicInteger();

        LocalFileArtifactStore store = new LocalFileArtifactStore(new ObjectMapper(), temp.toString()) {
            @Override
            protected byte[] readCanonicalBytes(Path path) {
                byte[] validatedBytes = super.readCanonicalBytes(path);
                if (reads.incrementAndGet() == 1) {
                    try {
                        Files.write(path, "{\"replaced\":true}".getBytes(StandardCharsets.UTF_8));
                    } catch (java.io.IOException exception) {
                        throw new AssertionError(exception);
                    }
                }
                return validatedBytes;
            }
        };

        ArtifactStore.VerifiedArtifact verified = store.readVerifiedArtifact(reference, "RUN", entityId);

        assertEquals(1, reads.get());
        assertEquals(entityId, verified.document().path("run").path("run_id").asText());
        assertEquals(contentHash, verified.snapshot().contentSha256());
    }

    private static String sha256(byte[] content) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
    }
}
