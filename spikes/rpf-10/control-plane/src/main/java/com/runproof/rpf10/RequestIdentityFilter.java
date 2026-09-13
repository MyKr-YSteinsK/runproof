package com.runproof.rpf10;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

/** Generates a non-secret correlation identity for audit records and errors. */
@Component
public class RequestIdentityFilter extends OncePerRequestFilter {

    public static final String REQUEST_ID_ATTRIBUTE = RequestIdentityFilter.class.getName() + ".requestId";
    public static final String REQUEST_ID_HEADER = "X-Request-Id";

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
        filterChain.doFilter(request, response);
    }
}
