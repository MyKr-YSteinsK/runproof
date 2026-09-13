package com.runproof.controlplane;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

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
        String principal = String.valueOf(request.getAttribute(RequestIdentityFilter.PRINCIPAL_ATTRIBUTE));
        String entityType = value(request.getAttribute("rpf.control-plane.entity-type"));
        String entityId = value(request.getAttribute("rpf.control-plane.entity-id"));
        String reason = value(request.getAttribute("rpf.control-plane.reason"));
        String requestId = value(request.getAttribute(RequestIdentityFilter.REQUEST_ID_ATTRIBUTE));
        auditService.record(
                principal,
                request.getMethod() + " " + request.getRequestURI(),
                entityType,
                entityId,
                "HTTP_" + response.getStatus(),
                requestId,
                reason
        );
    }

    private static String value(Object value) {
        return value == null ? "unknown" : String.valueOf(value);
    }
}
