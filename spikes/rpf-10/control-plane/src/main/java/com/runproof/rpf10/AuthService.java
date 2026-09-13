package com.runproof.rpf10;

import jakarta.annotation.PostConstruct;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import java.util.Set;

import static com.runproof.rpf10.ProbeExceptions.AuthenticationRequiredException;
import static com.runproof.rpf10.ProbeExceptions.AuthorizationForbiddenException;

/**
 * Minimal service-to-service bearer credential candidate. Tokens are supplied
 * through the process environment and are never part of a response or audit
 * record. This is intentionally not OAuth/OIDC or a user-session system.
 */
@Component
public class AuthService {

    public static final String PRINCIPAL_ATTRIBUTE = AuthService.class.getName() + ".principal";
    public static final String FAILURE_ATTRIBUTE = AuthService.class.getName() + ".failure";

    private final String readToken;
    private final String evidenceToken;
    private final String decisionToken;
    private final String agentToken;
    private Map<String, PrincipalCredential> credentials;

    public AuthService(
            @Value("${rpf.auth.read-token:}") String readToken,
            @Value("${rpf.auth.evidence-token:}") String evidenceToken,
            @Value("${rpf.auth.decision-token:}") String decisionToken,
            @Value("${rpf.auth.agent-token:}") String agentToken
    ) {
        this.readToken = readToken;
        this.evidenceToken = evidenceToken;
        this.decisionToken = decisionToken;
        this.agentToken = agentToken;
    }

    @PostConstruct
    void validateConfiguration() {
        if (readToken.isBlank() || evidenceToken.isBlank() || decisionToken.isBlank() || agentToken.isBlank()) {
            throw new IllegalStateException("All disposable RPF-10 service credentials must be supplied through the environment.");
        }
        if (Set.of(readToken, evidenceToken, decisionToken, agentToken).size() != 4) {
            throw new IllegalStateException("RPF-10 service credentials must be distinct.");
        }
        credentials = Map.of(
                "read-service", new PrincipalCredential(readToken, new Principal("read-service", Set.of("metadata:read"))),
                "evidence-ingest-service", new PrincipalCredential(evidenceToken, new Principal("evidence-ingest-service", Set.of("evidence:write"))),
                "decision-writer-service", new PrincipalCredential(decisionToken, new Principal("decision-writer-service", Set.of("decision:write", "metadata:read"))),
                "agent-runtime", new PrincipalCredential(agentToken, new Principal("agent-runtime", Set.of("agent:observe")))
        );
    }

    public Principal authenticate(HttpServletRequest request) {
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ") || header.length() <= "Bearer ".length()) {
            request.setAttribute(FAILURE_ATTRIBUTE, "anonymous");
            throw new AuthenticationRequiredException();
        }
        String presented = header.substring("Bearer ".length());
        for (PrincipalCredential credential : credentials.values()) {
            if (sameSecret(presented, credential.token())) {
                request.setAttribute(PRINCIPAL_ATTRIBUTE, credential.principal());
                return credential.principal();
            }
        }
        request.setAttribute(FAILURE_ATTRIBUTE, "unknown-credential");
        throw new AuthenticationRequiredException();
    }

    public Principal require(HttpServletRequest request, String scope) {
        Object value = request.getAttribute(PRINCIPAL_ATTRIBUTE);
        Principal principal = value instanceof Principal current ? current : authenticate(request);
        if (!principal.hasScope(scope)) {
            throw new AuthorizationForbiddenException(scope);
        }
        return principal;
    }

    private static boolean sameSecret(String presented, String configured) {
        return MessageDigest.isEqual(
                presented.getBytes(StandardCharsets.UTF_8),
                configured.getBytes(StandardCharsets.UTF_8)
        );
    }

    private record PrincipalCredential(String token, Principal principal) {
    }
}
