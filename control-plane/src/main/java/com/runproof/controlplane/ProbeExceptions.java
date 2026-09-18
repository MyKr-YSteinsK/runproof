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

    static class ArtifactStoreException extends RuntimeException {
        private final String code;
        private final boolean retriable;

        ArtifactStoreException(String code, String message, boolean retriable) {
            super(message);
            this.code = code;
            this.retriable = retriable;
        }

        String code() {
            return code;
        }

        boolean retriable() {
            return retriable;
        }
    }

    static class IdentityConflictException extends RuntimeException {
        private final String code;

        IdentityConflictException(String message) {
            this("IDENTITY_CONTENT_CONFLICT", message);
        }

        IdentityConflictException(String code, String message) {
            super(message);
            this.code = code;
        }

        String code() {
            return code;
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
