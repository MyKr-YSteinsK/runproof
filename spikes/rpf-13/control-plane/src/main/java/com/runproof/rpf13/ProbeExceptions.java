package com.runproof.rpf13;

import org.springframework.http.HttpStatus;

final class ProbeExceptions {

    private ProbeExceptions() {
    }

    static class ApiException extends RuntimeException {
        private final HttpStatus status;
        private final String code;
        private final boolean retriable;

        ApiException(HttpStatus status, String code, String message, boolean retriable) {
            super(message);
            this.status = status;
            this.code = code;
            this.retriable = retriable;
        }

        HttpStatus status() {
            return status;
        }

        String code() {
            return code;
        }

        boolean retriable() {
            return retriable;
        }
    }

    static ApiException badRequest(String code, String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, code, message, false);
    }

    static ApiException notFound(String message) {
        return new ApiException(HttpStatus.NOT_FOUND, "JOB_NOT_FOUND", message, false);
    }

    static ApiException conflict(String code, String message) {
        return new ApiException(HttpStatus.CONFLICT, code, message, false);
    }

    static ApiException reconcileRequired(String message) {
        return new ApiException(HttpStatus.CONFLICT, "RECONCILE_REQUIRED", message, false);
    }
}
