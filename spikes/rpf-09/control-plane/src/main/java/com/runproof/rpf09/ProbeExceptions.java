package com.runproof.rpf09;

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

    static class RollbackProbeException extends RuntimeException {
        RollbackProbeException() {
            super("The disposable rollback probe intentionally aborted its transaction.");
        }
    }
}
