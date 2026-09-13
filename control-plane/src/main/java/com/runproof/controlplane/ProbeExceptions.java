package com.runproof.controlplane;

final class ProbeExceptions {

    private ProbeExceptions() {
    }

    static class RequestValidationException extends RuntimeException {
        private final String code;

        RequestValidationException(String code, String message) {
            super(message);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static class InvalidEvidenceException extends RuntimeException {
        private final String code;

        InvalidEvidenceException(String code, String message) {
            super(message);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static class IdentityConflictException extends RuntimeException {
        IdentityConflictException(String message) {
            super(message);
        }
    }

    static class EntityNotFoundException extends RuntimeException {
        EntityNotFoundException(String message) {
            super(message);
        }
    }

    static class AuthenticationRequiredException extends RuntimeException {
        AuthenticationRequiredException() {
            super("A valid service credential is required.");
        }
    }

    static class AuthorizationForbiddenException extends RuntimeException {
        AuthorizationForbiddenException(String scope) {
            super("The authenticated principal does not have the required scope: " + scope + ".");
        }
    }

    static class ProbeRollbackException extends RuntimeException {
        ProbeRollbackException() {
            super("The controlled rollback test intentionally aborted its transaction.");
        }
    }
}
