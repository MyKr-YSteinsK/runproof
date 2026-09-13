package com.runproof.controlplane;

import jakarta.annotation.PostConstruct;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import static com.runproof.controlplane.ProbeExceptions.AuthenticationRequiredException;
import static com.runproof.controlplane.ProbeExceptions.AuthorizationForbiddenException;

@Service
public class AuthService {

    private final Map<String, Credential> credentials = new LinkedHashMap<>();

    @Value("${rpf.auth.read-token:}")
    private String readToken;

    @Value("${rpf.auth.evidence-token:}")
    private String evidenceToken;

    @Value("${rpf.auth.decision-token:}")
    private String decisionToken;

    @Value("${rpf.auth.agent-token:}")
    private String agentToken;

    @Value("${rpf.auth.ci-token:}")
    private String ciToken;

    @PostConstruct
    void initialize() {
        credentials.clear();
        add("read-service", readToken, Set.of("metadata:read"));
        add("evidence-ingest-service", evidenceToken, Set.of("evidence:write"));
        add("decision-writer-service", decisionToken, Set.of("decision:write", "metadata:read"));
        add("agent-runtime", agentToken, Set.of("agent:observe"));
        add("ci-service", ciToken, Set.of("metadata:read", "evidence:write"));
    }

    public Principal authenticate(HttpServletRequest request) {
        String header = request.getHeader("Authorization");
        Principal principal = null;
        if (header != null && header.startsWith("Bearer ") && header.length() > 7) {
            byte[] supplied = header.substring(7).getBytes(StandardCharsets.UTF_8);
            for (Credential credential : credentials.values()) {
                byte[] expected = credential.token().getBytes(StandardCharsets.UTF_8);
                if (MessageDigest.isEqual(supplied, expected)) {
                    principal = new Principal(credential.id(), credential.scopes());
                    break;
                }
            }
        }
        if (principal == null) {
            request.setAttribute(RequestIdentityFilter.PRINCIPAL_ATTRIBUTE, "anonymous");
            throw new AuthenticationRequiredException();
        }
        request.setAttribute(RequestIdentityFilter.PRINCIPAL_ATTRIBUTE, principal.id());
        request.setAttribute("rpf.control-plane.principal", principal);
        return principal;
    }

    public Principal require(HttpServletRequest request, String scope) {
        Object value = request.getAttribute("rpf.control-plane.principal");
        Principal principal = value instanceof Principal found ? found : authenticate(request);
        if (!principal.hasScope(scope)) {
            throw new AuthorizationForbiddenException(scope);
        }
        return principal;
    }

    private void add(String id, String token, Set<String> scopes) {
        if (token == null || token.isBlank()) {
            throw new IllegalStateException("Missing required service credential configuration for " + id + ".");
        }
        for (Credential existing : credentials.values()) {
            if (MessageDigest.isEqual(existing.token().getBytes(StandardCharsets.UTF_8), token.getBytes(StandardCharsets.UTF_8))) {
                throw new IllegalStateException("Service credentials must be distinct.");
            }
        }
        credentials.put(id, new Credential(id, token, scopes));
    }

    private record Credential(String id, String token, Set<String> scopes) {
    }
}
