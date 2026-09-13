package com.runproof.rpf09;

import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import static com.runproof.rpf09.ProbeExceptions.EntityNotFoundException;
import static com.runproof.rpf09.ProbeExceptions.IdentityConflictException;
import static com.runproof.rpf09.ProbeExceptions.InvalidEvidenceException;
import static com.runproof.rpf09.ProbeExceptions.RequestValidationException;
import static com.runproof.rpf09.ProbeExceptions.RollbackProbeException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(RequestValidationException.class)
    ResponseEntity<ApiModels.ApiError> requestValidation(RequestValidationException exception) {
        return error(HttpStatus.BAD_REQUEST, exception.code(), exception.getMessage(), false, null);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiModels.ApiError> malformedJson(HttpMessageNotReadableException exception) {
        return error(HttpStatus.BAD_REQUEST, "REQUEST_VALIDATION_ERROR", "Request JSON is malformed or incomplete.", false, null);
    }

    @ExceptionHandler(InvalidEvidenceException.class)
    ResponseEntity<ApiModels.ApiError> invalidEvidence(InvalidEvidenceException exception) {
        return error(HttpStatus.UNPROCESSABLE_ENTITY, exception.code(), exception.getMessage(), false, false);
    }

    @ExceptionHandler(IdentityConflictException.class)
    ResponseEntity<ApiModels.ApiError> identityConflict(IdentityConflictException exception) {
        return error(HttpStatus.CONFLICT, "IDENTITY_CONTENT_CONFLICT", exception.getMessage(), false, false);
    }

    @ExceptionHandler(EntityNotFoundException.class)
    ResponseEntity<ApiModels.ApiError> notFound(EntityNotFoundException exception) {
        return error(HttpStatus.NOT_FOUND, "CANONICAL_METADATA_NOT_FOUND", exception.getMessage(), false, null);
    }

    @ExceptionHandler(RollbackProbeException.class)
    ResponseEntity<ApiModels.ApiError> rollback(RollbackProbeException exception) {
        return error(HttpStatus.INTERNAL_SERVER_ERROR, "PROBE_TRANSACTION_ROLLED_BACK", exception.getMessage(), false, null);
    }

    @ExceptionHandler(DataAccessException.class)
    ResponseEntity<ApiModels.ApiError> storage(DataAccessException exception) {
        return error(HttpStatus.SERVICE_UNAVAILABLE, "PLATFORM_STORAGE_UNAVAILABLE", "Canonical metadata storage is unavailable.", true, null);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiModels.ApiError> unexpected(Exception exception) {
        return error(HttpStatus.INTERNAL_SERVER_ERROR, "PLATFORM_INTERNAL_ERROR", "The Control Plane probe could not complete the request.", false, null);
    }

    private static ResponseEntity<ApiModels.ApiError> error(
            HttpStatus status,
            String code,
            String message,
            boolean retriable,
            Boolean evidenceValid
    ) {
        return ResponseEntity.status(status).body(new ApiModels.ApiError(code, message, retriable, evidenceValid));
    }
}
