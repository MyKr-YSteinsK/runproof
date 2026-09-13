package com.runproof.rpf13;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.LinkedHashMap;
import java.util.Map;

import static com.runproof.rpf13.ProbeExceptions.ApiException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ApiException.class)
    ResponseEntity<Map<String, Object>> api(ApiException exception, HttpServletRequest request) {
        return error(exception.status(), exception.code(), exception.getMessage(), exception.retriable(), request);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<Map<String, Object>> malformed(HttpMessageNotReadableException exception, HttpServletRequest request) {
        return error(HttpStatus.BAD_REQUEST, "REQUEST_VALIDATION_ERROR", "Request JSON is malformed or incomplete.", false, request);
    }

    @ExceptionHandler(DataAccessException.class)
    ResponseEntity<Map<String, Object>> storage(DataAccessException exception, HttpServletRequest request) {
        return error(HttpStatus.SERVICE_UNAVAILABLE, "PLATFORM_STORAGE_UNAVAILABLE", "Durable execution storage is unavailable.", true, request);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<Map<String, Object>> unexpected(Exception exception, HttpServletRequest request) {
        return error(HttpStatus.INTERNAL_SERVER_ERROR, "PLATFORM_INTERNAL_ERROR", "The durable execution candidate could not complete the request.", false, request);
    }

    private static ResponseEntity<Map<String, Object>> error(
            HttpStatus status,
            String code,
            String message,
            boolean retriable,
            HttpServletRequest request
    ) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("error", code);
        body.put("message", message);
        body.put("retriable", retriable);
        body.put("correlation_id", request.getHeader("X-Correlation-Id") == null ? "rpf13-http" : request.getHeader("X-Correlation-Id"));
        return ResponseEntity.status(status).body(body);
    }
}
