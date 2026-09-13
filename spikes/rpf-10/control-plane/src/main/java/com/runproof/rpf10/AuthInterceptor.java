package com.runproof.rpf10;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

import java.util.Map;

/** Authenticates every protected API request and records an audit identity. */
public class AuthInterceptor implements HandlerInterceptor {

    private final AuthService authService;
    private final AuditService auditService;

    public AuthInterceptor(AuthService authService, AuditService auditService) {
        this.authService = authService;
        this.auditService = auditService;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        authService.authenticate(request);
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception
    ) {
        Object principalValue = request.getAttribute(AuthService.PRINCIPAL_ATTRIBUTE);
        Object failureValue = request.getAttribute(AuthService.FAILURE_ATTRIBUTE);
        String principalId = principalValue instanceof Principal principal
                ? principal.id()
                : failureValue instanceof String failure ? failure : "anonymous";
        String action = request.getAttribute("rpf10.audit.action") instanceof String marked
                ? marked
                : request.getMethod() + " " + request.getRequestURI();
        String entityId = request.getAttribute("rpf10.audit.entity") instanceof String marked
                ? marked
                : pathEntityId(request);
        String result = exception == null ? "HTTP_" + response.getStatus() : "EXCEPTION_" + response.getStatus();
        String requestId = String.valueOf(request.getAttribute(RequestIdentityFilter.REQUEST_ID_ATTRIBUTE));
        auditService.record(principalId, action, entityId, result, requestId);
    }

    private static String pathEntityId(HttpServletRequest request) {
        Object variables = request.getAttribute("org.springframework.web.servlet.HandlerMapping.uriTemplateVariables");
        if (variables instanceof Map<?, ?> map && map.get("entityId") instanceof String entityId) {
            return entityId;
        }
        return null;
    }
}
