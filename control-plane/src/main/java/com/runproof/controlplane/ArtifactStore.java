package com.runproof.controlplane;

import com.fasterxml.jackson.databind.JsonNode;

public interface ArtifactStore {

    ApiModels.ArtifactSnapshot verify(ApiModels.ArtifactRef reference, String entityType, String entityId);

    VerifiedArtifact readVerifiedArtifact(ApiModels.ArtifactRef reference, String entityType, String entityId);

    default JsonNode readVerified(ApiModels.ArtifactRef reference, String entityType, String entityId) {
        return readVerifiedArtifact(reference, entityType, entityId).document();
    }

    PathWriteResult put(String artifactKey, byte[] content);

    boolean isAvailable();

    record PathWriteResult(String artifactKey, String contentSha256, boolean alreadyExists) {
    }

    record VerifiedArtifact(ApiModels.ArtifactSnapshot snapshot, JsonNode document) {
    }
}
