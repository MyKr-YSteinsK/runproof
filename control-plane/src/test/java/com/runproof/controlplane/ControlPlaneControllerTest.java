package com.runproof.controlplane;

import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ControlPlaneControllerTest {

    private AuthService authService;
    private CanonicalMetadataService metadataService;
    private ControlPlaneController controller;

    @BeforeEach
    void configureController() {
        authService = new AuthService();
        ReflectionTestUtils.setField(authService, "readToken", "read-token");
        ReflectionTestUtils.setField(authService, "evidenceToken", "evidence-token");
        ReflectionTestUtils.setField(authService, "decisionToken", "decision-token");
        ReflectionTestUtils.setField(authService, "agentToken", "agent-token");
        ReflectionTestUtils.setField(authService, "ciToken", "ci-token");
        ReflectionTestUtils.setField(authService, "workerToken", "worker-token");
        authService.initialize();
        metadataService = mock(CanonicalMetadataService.class);
        controller = new ControlPlaneController(
                mock(PersistenceSchema.class),
                mock(LocalFileArtifactStore.class),
                metadataService,
                mock(AuditService.class),
                authService,
                false
        );
    }

    @Test
    void evidenceOnlyCannotRegisterStatisticalDecisionThroughEvidenceEndpoint() {
        assertThrows(
                ProbeExceptions.AuthorizationForbiddenException.class,
                () -> controller.ingest(request("evidence-token"), statisticalDecisionManifest(), false)
        );
    }

    @Test
    void decisionWriterCanRegisterStatisticalDecisionThroughDecisionEndpoint() {
        when(metadataService.ingest(any(), eq("decision-writer-service"), eq(false)))
                .thenReturn(new ApiModels.IngestResponse("INGESTED", false, null));

        var response = controller.registerDecision(request("decision-token"), statisticalDecisionManifest(), false);

        assertEquals(201, response.getStatusCode().value());
    }

    @Test
    void workerAndAgentCannotUseDecisionEndpointForStatisticalDecision() {
        assertThrows(
                ProbeExceptions.AuthorizationForbiddenException.class,
                () -> controller.registerDecision(request("worker-token"), statisticalDecisionManifest(), false)
        );
        assertThrows(
                ProbeExceptions.AuthorizationForbiddenException.class,
                () -> controller.registerDecision(request("agent-token"), statisticalDecisionManifest(), false)
        );
    }

    @Test
    void malformedEvidenceManifestReachesCanonicalValidationInsteadOfNullSetFailure() {
        when(metadataService.ingest(any(), eq("evidence-ingest-service"), eq(false)))
                .thenThrow(new ProbeExceptions.RequestValidationException("UNKNOWN_MANIFEST_SCHEMA", "Manifest schema is not accepted."));

        var malformed = new ApiModels.IngestManifest(
                "unknown", null, null, null, null, null, null, null, null, null, null, null, null
        );

        assertThrows(
                ProbeExceptions.RequestValidationException.class,
                () -> controller.ingest(request("evidence-token"), malformed, false)
        );
    }

    private static HttpServletRequest request(String token) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("Authorization", "Bearer " + token);
        return request;
    }

    private static ApiModels.IngestManifest statisticalDecisionManifest() {
        return new ApiModels.IngestManifest(
                "rpf-canonical-ingest-v1",
                "STATISTICAL_RELEASE_DECISION",
                "statistical-decision-test",
                "rpf-statistical-release-decision-v1",
                "ELIGIBLE",
                null,
                null,
                "statistical-decision-test:idempotency",
                null,
                null,
                java.util.List.of(),
                java.util.Map.of(),
                null
        );
    }
}
