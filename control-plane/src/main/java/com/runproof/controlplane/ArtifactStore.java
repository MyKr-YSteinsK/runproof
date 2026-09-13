package com.runproof.controlplane;

import com.fasterxml.jackson.databind.JsonNode;

public interface ArtifactStore {

    ApiModels.ArtifactSnapshot verify(ApiModels.ArtifactRef reference, String entityType, String entityId);

    JsonNode readVerified(ApiModels.ArtifactRef reference, String entityType, String entityId);

    PathWriteResult put(String artifactKey, byte[] content);

    boolean isAvailable();

    record PathWriteResult(String artifactKey, String contentSha256, boolean alreadyExists) {
    }
}
