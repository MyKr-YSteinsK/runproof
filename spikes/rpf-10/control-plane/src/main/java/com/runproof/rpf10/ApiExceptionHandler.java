package com.runproof.rpf10;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import static com.runproof.rpf10.ProbeExceptions.AuthenticationRequiredException;
import static com.runproof.rpf10.ProbeExceptions.AuthorizationForbiddenException;
import static com.runproof.rpf10.ProbeExceptions.EntityNotFoundException;
import static com.runproof.rpf10.ProbeExceptions.IdentityConflictException;
import static com.runproof.rpf10.ProbeExceptions.InvalidEvidenceException;
import static com.runproof.rpf10.ProbeExceptions.RequestValidationException;
import static com.runproof.rpf10.ProbeExceptions.RollbackProbeException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(AuthenticationRequiredException.class)
    ResponseEntity<ApiModels.ApiError> authentication(AuthenticationRequiredException exception, HttpServletRequest request) {
        return error(HttpStatus.UNAUTHORIZED, "AUTHENTICATION_REQUIRED", "A valid service credential is required.", false, null, request);
    }

    @ExceptionHandler(AuthorizationForbiddenException.class)
    ResponseEntity<ApiModels.ApiError> authorization(AuthorizationForbiddenException exception, HttpServletRequest request) {
        return error(HttpStatus.FORBIDDEN, "AUTHORIZATION_FORBIDDEN", "The authenticated principal is not authorized for this action.", false, null, request);
    }

    @ExceptionHandler(RequestValidationException.class)
    ResponseEntity<ApiModels.ApiError> requestValidation(RequestValidationException exception, HttpServletRequest request) {
        return error(HttpStatus.BAD_REQUEST, exception.code(), exception.getMessage(), false, null, request);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiModels.ApiError> malformedJson(HttpMessageNotReadableException exception, HttpServletRequest request) {
        return error(HttpStatus.BAD_REQUEST, "REQUEST_VALIDATION_ERROR", "Request JSON is malformed or incomplete.", false, null, request);
    }

    @ExceptionHandler(InvalidEvidenceException.class)
    ResponseEntity<ApiModels.ApiError> invalidEvidence(InvalidEvidenceException exception, HttpServletRequest request) {
        return error(HttpStatus.UNPROCESSABLE_ENTITY, exception.code(), exception.getMessage(), false, false, request);
    }

    @ExceptionHandler(IdentityConflictException.class)
    ResponseEntity<ApiModels.ApiError> identityConflict(IdentityConflictException exception, HttpServletRequest request) {
        return error(HttpStatus.CONFLICT, "IDENTITY_CONTENT_CONFLICT", exception.getMessage(), false, false, request);
    }

    @ExceptionHandler(EntityNotFoundException.class)
    ResponseEntity<ApiModels.ApiError> notFound(EntityNotFoundException exception, HttpServletRequest request) {
        return error(HttpStatus.NOT_FOUND, "CANONICAL_METADATA_NOT_FOUND", exception.getMessage(), false, null, request);
    }

    @ExceptionHandler(RollbackProbeException.class)
    ResponseEntity<ApiModels.ApiError> rollback(RollbackProbeException exception, HttpServletRequest request) {
        return error(HttpStatus.INTERNAL_SERVER_ERROR, "PROBE_TRANSACTION_ROLLED_BACK", exception.getMessage(), false, null, request);
    }

    @ExceptionHandler(DataAccessException.class)
    ResponseEntity<ApiModels.ApiError> storage(DataAccessException exception, HttpServletRequest request) {
        return error(HttpStatus.SERVICE_UNAVAILABLE, "PLATFORM_STORAGE_UNAVAILABLE", "Canonical metadata storage is unavailable.", true, null, request);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiModels.ApiError> unexpected(Exception exception, HttpServletRequest request) {
        return error(HttpStatus.INTERNAL_SERVER_ERROR, "PLATFORM_INTERNAL_ERROR", "The Control Plane probe could not complete the request.", false, null, request);
    }

    private static ResponseEntity<ApiModels.ApiError> error(
            HttpStatus status,
            String code,
            String message,
            boolean retriable,
            Boolean evidenceValid,
            HttpServletRequest request
    ) {
        Object requestId = request.getAttribute(RequestIdentityFilter.REQUEST_ID_ATTRIBUTE);
        String correlationId = requestId instanceof String value ? value : "unknown";
        return ResponseEntity.status(status).body(new ApiModels.ApiError(code, message, retriable, evidenceValid, correlationId));
    }
}
