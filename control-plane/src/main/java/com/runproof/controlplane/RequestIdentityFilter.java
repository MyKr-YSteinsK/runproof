package com.runproof.controlplane;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.regex.Pattern;
import java.util.UUID;

@Component
public class RequestIdentityFilter extends OncePerRequestFilter {

    public static final String REQUEST_ID_ATTRIBUTE = RequestIdentityFilter.class.getName() + ".requestId";
    public static final String PRINCIPAL_ATTRIBUTE = RequestIdentityFilter.class.getName() + ".principal";
    public static final String REQUEST_ID_HEADER = "X-Request-Id";
    private static final Pattern JOB_ROUTE = Pattern.compile("/api/v1/jobs/[^/]+(?:/[^/]+)?");
    private static final Pattern METADATA_ROUTE = Pattern.compile("/api/v1/metadata/[^/]+(?:/[^/]+)?");

    private final ObservabilityService observability;

    public RequestIdentityFilter(ObservabilityService observability) {
        this.observability = observability;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String supplied = request.getHeader(REQUEST_ID_HEADER);
        String requestId = supplied != null && supplied.matches("[A-Za-z0-9._:-]{1,96}")
                ? supplied
                : UUID.randomUUID().toString();
        request.setAttribute(REQUEST_ID_ATTRIBUTE, requestId);
        response.setHeader(REQUEST_ID_HEADER, requestId);
        ObservabilityService.SpanScope span = observability.httpSpan(request, routeFor(request.getRequestURI()));
        try {
            filterChain.doFilter(request, response);
        } catch (ServletException | IOException | RuntimeException exception) {
            span.error(exception, "http_request_error");
            throw exception;
        } finally {
            if (span.valid()) span.span().setAttribute("http.status_code", response.getStatus());
            span.close();
        }
    }

    private static String routeFor(String uri) {
        if (uri == null || uri.isBlank()) return "unknown";
        if (JOB_ROUTE.matcher(uri).matches()) {
            String[] parts = uri.split("/");
            return parts.length >= 6 ? "/api/v1/jobs/{job_id}/{operation}" : "/api/v1/jobs/{job_id}";
        }
        if (METADATA_ROUTE.matcher(uri).matches()) return "/api/v1/metadata/{entity_type}/{entity_id}";
        if (uri.startsWith("/api/v1/metadata")) return "/api/v1/metadata";
        if (uri.startsWith("/api/v1/release-decisions")) return "/api/v1/release-decisions";
        if (uri.startsWith("/api/v1/")) return "/api/v1/endpoint";
        return uri;
    }
}
