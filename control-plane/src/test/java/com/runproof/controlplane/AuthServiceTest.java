package com.runproof.controlplane;

import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AuthServiceTest {

    private final AuthService service = new AuthService();

    @BeforeEach
    void configureDistinctServiceCredentials() {
        ReflectionTestUtils.setField(service, "readToken", "read-token");
        ReflectionTestUtils.setField(service, "evidenceToken", "evidence-token");
        ReflectionTestUtils.setField(service, "decisionToken", "decision-token");
        ReflectionTestUtils.setField(service, "agentToken", "agent-token");
        ReflectionTestUtils.setField(service, "ciToken", "ci-token");
        service.initialize();
    }

    @Test
    void mapsPrincipalsToNarrowScopes() {
        Principal read = service.authenticate(request("read-token"));
        Principal decision = service.authenticate(request("decision-token"));

        assertEquals("read-service", read.id());
        assertEquals("decision-writer-service", decision.id());
        assertThrows(ProbeExceptions.AuthorizationForbiddenException.class, () -> service.require(request("evidence-token"), "decision:write"));
    }

    @Test
    void rejectsMissingAndInvalidCredentials() {
        assertThrows(ProbeExceptions.AuthenticationRequiredException.class, () -> service.authenticate(new MockHttpServletRequest()));
        assertThrows(ProbeExceptions.AuthenticationRequiredException.class, () -> service.authenticate(request("not-a-token")));
    }

    @Test
    void rejectsDuplicateCredentialConfiguration() {
        ReflectionTestUtils.setField(service, "decisionToken", "read-token");
        assertThrows(IllegalStateException.class, service::initialize);
    }

    private static HttpServletRequest request(String token) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("Authorization", "Bearer " + token);
        return request;
    }
}
