package com.runproof.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class S3ArtifactStoreTest {

    @Test
    void verifiedReadUsesOneBodyGetForHashAndIdentityChecks() throws Exception {
        String entityId = "s3-read-001";
        String sourceHash = "a".repeat(64);
        byte[] content = new ObjectMapper().writeValueAsBytes(Map.of(
                "artifact_kind", "Run Evidence",
                "schema_version", "rpf-run-evidence-v2",
                "source_sha256", sourceHash,
                "runtime_version", "runtime-s3-test-v1",
                "run", Map.of("run_id", entityId),
                "trajectory", Map.of("events", java.util.List.of())
        ));
        String contentHash = sha256(content);
        String key = "run/" + entityId + "/" + contentHash + ".json";
        S3Client client = mock(S3Client.class);
        when(client.getObjectAsBytes(any(software.amazon.awssdk.services.s3.model.GetObjectRequest.class))).thenReturn(ResponseBytes.fromByteArray(GetObjectResponse.builder().build(), content));
        S3ArtifactStore store = new S3ArtifactStore(new ObjectMapper(), client, "runproof", "rpf32/");

        ArtifactStore.VerifiedArtifact verified = store.readVerifiedArtifact(
                new ApiModels.ArtifactRef(entityId, key, "Run Evidence", "rpf-run-evidence-v2", contentHash, sourceHash, "runtime-s3-test-v1"),
                "RUN",
                entityId
        );

        assertTrue(verified.snapshot().resolved());
        assertEquals(entityId, verified.document().path("run").path("run_id").asText());
        verify(client, times(1)).getObjectAsBytes(any(software.amazon.awssdk.services.s3.model.GetObjectRequest.class));
    }

    @Test
    void conditionalFailureReconcilesSameBytesAndRejectsDifferentBytes() {
        byte[] original = "original".getBytes(StandardCharsets.UTF_8);
        S3Client client = mock(S3Client.class);
        when(client.putObject(any(PutObjectRequest.class), any(software.amazon.awssdk.core.sync.RequestBody.class)))
                .thenThrow(S3Exception.builder().statusCode(412).build());
        when(client.getObjectAsBytes(any(software.amazon.awssdk.services.s3.model.GetObjectRequest.class))).thenReturn(ResponseBytes.fromByteArray(GetObjectResponse.builder().build(), original));
        S3ArtifactStore store = new S3ArtifactStore(new ObjectMapper(), client, "runproof", "rpf32/");

        assertTrue(store.put("run/same/key.json", original).alreadyExists());
        ProbeExceptions.InvalidEvidenceException conflict = assertThrows(
                ProbeExceptions.InvalidEvidenceException.class,
                () -> store.put("run/same/key.json", "changed".getBytes(StandardCharsets.UTF_8))
        );
        assertEquals("ARTIFACT_OVERWRITE_REJECTED", conflict.code());
    }

    @Test
    void unknownPutOutcomeReconcilesObjectBeforeRetrying() {
        byte[] content = "response-lost".getBytes(StandardCharsets.UTF_8);
        S3Client client = mock(S3Client.class);
        when(client.putObject(any(PutObjectRequest.class), any(software.amazon.awssdk.core.sync.RequestBody.class)))
                .thenThrow(SdkClientException.create("response lost"));
        when(client.getObjectAsBytes(any(software.amazon.awssdk.services.s3.model.GetObjectRequest.class))).thenReturn(ResponseBytes.fromByteArray(GetObjectResponse.builder().build(), content));
        S3ArtifactStore store = new S3ArtifactStore(new ObjectMapper(), client, "runproof", "rpf32/");

        assertTrue(store.put("run/unknown/key.json", content).alreadyExists());
        verify(client, times(1)).getObjectAsBytes(any(software.amazon.awssdk.services.s3.model.GetObjectRequest.class));
    }

    @Test
    void missingObjectIsDifferentFromBackendFailure() {
        S3Client client = mock(S3Client.class);
        when(client.getObjectAsBytes(any(software.amazon.awssdk.services.s3.model.GetObjectRequest.class))).thenThrow(S3Exception.builder().statusCode(404).build());
        S3ArtifactStore store = new S3ArtifactStore(new ObjectMapper(), client, "runproof", "rpf32/");
        ProbeExceptions.InvalidEvidenceException missing = assertThrows(
                ProbeExceptions.InvalidEvidenceException.class,
                () -> store.readVerifiedArtifact(
                        new ApiModels.ArtifactRef("run-missing", "run/run-missing/key.json", "Run Evidence", "rpf-run-evidence-v2", "0".repeat(64), "a".repeat(64), "runtime-v1"),
                        "RUN",
                        "run-missing"
                )
        );
        assertEquals("INVALID_EVIDENCE_ARTIFACT_MISSING", missing.code());
    }

    private static String sha256(byte[] content) throws Exception {
        return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
    }
}
