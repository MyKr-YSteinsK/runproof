package com.runproof.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.core.checksums.RequestChecksumCalculation;
import software.amazon.awssdk.core.checksums.ResponseChecksumValidation;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.core.retry.RetryPolicy;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.http.urlconnection.UrlConnectionHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadBucketRequest;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;

import java.net.URI;
import java.time.Duration;
import java.util.Arrays;
import java.util.Objects;

import static com.runproof.controlplane.ProbeExceptions.ArtifactStoreException;
import static com.runproof.controlplane.ProbeExceptions.InvalidEvidenceException;

/**
 * AWS SDK v2 adapter for an S3-compatible immutable artifact store.
 *
 * The adapter owns provider-specific requests and credentials. The rest of
 * the Control Plane sees only the provider-neutral {@link ArtifactStore}
 * contract and canonical artifact references.
 */
@Component
@ConditionalOnProperty(name = "rpf.artifact-store.backend", havingValue = "s3")
public class S3ArtifactStore implements ArtifactStore {

    private static final String CONDITIONAL_CREATE = "*";
    private static final int UNKNOWN_OUTCOME_RETRIES = 1;

    private final ObjectMapper objectMapper;
    private final S3Client client;
    private final String bucket;
    private final String prefix;
    private final boolean closeClient;

    @Autowired
    public S3ArtifactStore(
            ObjectMapper objectMapper,
            @Value("${rpf.artifact-store.s3.endpoint:}") String endpoint,
            @Value("${rpf.artifact-store.s3.region:us-east-1}") String region,
            @Value("${rpf.artifact-store.s3.bucket:}") String bucket,
            @Value("${rpf.artifact-store.s3.prefix:}") String prefix,
            @Value("${rpf.artifact-store.s3.access-key:}") String accessKey,
            @Value("${rpf.artifact-store.s3.secret-key:}") String secretKey,
            @Value("${rpf.artifact-store.s3.path-style-access:true}") boolean pathStyleAccess,
            @Value("${rpf.artifact-store.s3.connect-timeout-ms:2000}") long connectTimeoutMs,
            @Value("${rpf.artifact-store.s3.api-timeout-ms:5000}") long apiTimeoutMs,
            @Value("${rpf.artifact-store.s3.attempt-timeout-ms:5000}") long attemptTimeoutMs
    ) {
        this(
                objectMapper,
                buildClient(endpoint, region, accessKey, secretKey, pathStyleAccess, connectTimeoutMs, apiTimeoutMs, attemptTimeoutMs),
                bucket,
                prefix,
                true
        );
    }

    S3ArtifactStore(ObjectMapper objectMapper, S3Client client, String bucket, String prefix) {
        this(objectMapper, client, bucket, prefix, false);
    }

    private S3ArtifactStore(ObjectMapper objectMapper, S3Client client, String bucket, String prefix, boolean closeClient) {
        this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
        this.client = Objects.requireNonNull(client, "client");
        this.bucket = requiredConfig(bucket, "RPF_ARTIFACT_STORE_S3_BUCKET");
        this.prefix = normalizePrefix(prefix);
        this.closeClient = closeClient;
    }

    @Override
    public ApiModels.ArtifactSnapshot verify(ApiModels.ArtifactRef reference, String entityType, String entityId) {
        return readVerifiedArtifact(reference, entityType, entityId).snapshot();
    }

    @Override
    public ArtifactStore.VerifiedArtifact readVerifiedArtifact(ApiModels.ArtifactRef reference, String entityType, String entityId) {
        ArtifactStoreSupport.validateReference(reference, entityType, entityId);
        String key = objectKey(reference == null ? null : reference.artifactKey());
        try {
            // One SDK GET returns the body used for every subsequent hash,
            // parse, schema, entity and source-identity check.
            ResponseBytes<software.amazon.awssdk.services.s3.model.GetObjectResponse> response = client.getObjectAsBytes(
                    GetObjectRequest.builder().bucket(bucket).key(key).build()
            );
            return ArtifactStoreSupport.verifyBytes(objectMapper, reference, entityType, entityId, response.asByteArray());
        } catch (NoSuchKeyException exception) {
            throw missingArtifact();
        } catch (S3Exception exception) {
            if (isMissing(exception)) throw missingArtifact();
            throw backendException(exception);
        } catch (SdkClientException exception) {
            throw new ArtifactStoreException("ARTIFACT_STORE_UNAVAILABLE", "Artifact storage is unavailable.", true);
        }
    }

    @Override
    public PathWriteResult put(String artifactKey, byte[] content) {
        String logicalKey = ArtifactStoreSupport.validateLogicalKey(artifactKey);
        byte[] bytes = Objects.requireNonNull(content, "content");
        String hash = ArtifactStoreSupport.sha256(bytes);
        String key = objectKey(logicalKey);
        try {
            conditionalPut(key, bytes);
            return new PathWriteResult(logicalKey, hash, false);
        } catch (S3Exception exception) {
            if (exception.statusCode() == 403 || "AccessDenied".equalsIgnoreCase(errorCode(exception))
                    || "InvalidAccessKeyId".equalsIgnoreCase(errorCode(exception))) {
                throw backendException(exception);
            }
            if (isConditionalFailure(exception)) {
                return reconcileAfterConditionalFailure(logicalKey, key, bytes, hash);
            }
            return reconcileUnknownOutcome(logicalKey, key, bytes, hash, exception);
        } catch (SdkClientException exception) {
            return reconcileUnknownOutcome(logicalKey, key, bytes, hash, exception);
        }
    }

    @Override
    public boolean isAvailable() {
        try {
            client.headBucket(HeadBucketRequest.builder().bucket(bucket).build());
            return true;
        } catch (S3Exception | SdkClientException exception) {
            return false;
        }
    }

    private void conditionalPut(String key, byte[] content) {
        client.putObject(
                PutObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .ifNoneMatch(CONDITIONAL_CREATE)
                        .contentLength((long) content.length)
                        .contentType("application/octet-stream")
                        .metadata(java.util.Map.of("rpf-sha256", ArtifactStoreSupport.sha256(content)))
                        .build(),
                RequestBody.fromBytes(content)
        );
    }

    private PathWriteResult reconcileAfterConditionalFailure(String logicalKey, String key, byte[] content, String hash) {
        byte[] existing = readExisting(key);
        return classifyExisting(logicalKey, content, hash, existing);
    }

    private PathWriteResult reconcileUnknownOutcome(String logicalKey, String key, byte[] content, String hash, Exception firstFailure) {
        for (int retry = 0; retry <= UNKNOWN_OUTCOME_RETRIES; retry++) {
            byte[] existing = tryReadExisting(key);
            if (existing != null) return classifyExisting(logicalKey, content, hash, existing);
            if (retry == UNKNOWN_OUTCOME_RETRIES) break;
            try {
                conditionalPut(key, content);
                return new PathWriteResult(logicalKey, hash, false);
            } catch (S3Exception exception) {
                if (isConditionalFailure(exception)) return reconcileAfterConditionalFailure(logicalKey, key, content, hash);
                firstFailure = exception;
            } catch (SdkClientException exception) {
                firstFailure = exception;
            }
        }
        throw new ArtifactStoreException("ARTIFACT_STORE_UNKNOWN_OUTCOME", "Artifact write outcome could not be reconciled.", true);
    }

    private byte[] readExisting(String key) {
        byte[] existing = tryReadExisting(key);
        if (existing == null) {
            throw new ArtifactStoreException("ARTIFACT_STORE_UNKNOWN_OUTCOME", "Conditional artifact write could not be reconciled.", true);
        }
        return existing;
    }

    private byte[] tryReadExisting(String key) {
        try {
            ResponseBytes<software.amazon.awssdk.services.s3.model.GetObjectResponse> response = client.getObjectAsBytes(
                    GetObjectRequest.builder().bucket(bucket).key(key).build()
            );
            return response.asByteArray();
        } catch (NoSuchKeyException exception) {
            return null;
        } catch (S3Exception exception) {
            if (isMissing(exception)) return null;
            throw backendException(exception);
        } catch (SdkClientException exception) {
            throw new ArtifactStoreException("ARTIFACT_STORE_UNAVAILABLE", "Artifact storage is unavailable.", true);
        }
    }

    private PathWriteResult classifyExisting(String logicalKey, byte[] content, String hash, byte[] existing) {
        if (!Arrays.equals(existing, content)) {
            throw new InvalidEvidenceException("ARTIFACT_OVERWRITE_REJECTED", "An immutable artifact key already contains different content.");
        }
        return new PathWriteResult(logicalKey, hash, true);
    }

    private String objectKey(String artifactKey) {
        String logicalKey = ArtifactStoreSupport.validateLogicalKey(artifactKey);
        return prefix + logicalKey;
    }

    private static boolean isConditionalFailure(S3Exception exception) {
        int status = exception.statusCode();
        String code = errorCode(exception);
        return status == 409 || status == 412
                || "PreconditionFailed".equalsIgnoreCase(code)
                || "ConditionalRequestConflict".equalsIgnoreCase(code);
    }

    private static boolean isMissing(S3Exception exception) {
        int status = exception.statusCode();
        String code = errorCode(exception);
        return status == 404 || "NoSuchKey".equalsIgnoreCase(code) || "NoSuchBucket".equalsIgnoreCase(code);
    }

    private static String errorCode(S3Exception exception) {
        return exception.awsErrorDetails() == null || exception.awsErrorDetails().errorCode() == null
                ? "" : exception.awsErrorDetails().errorCode();
    }

    private static ArtifactStoreException backendException(S3Exception exception) {
        if (exception.statusCode() == 403 || "AccessDenied".equalsIgnoreCase(errorCode(exception))) {
            return new ArtifactStoreException("ARTIFACT_STORE_ACCESS_DENIED", "Artifact storage denied the requested operation.", false);
        }
        return new ArtifactStoreException("ARTIFACT_STORE_UNAVAILABLE", "Artifact storage is unavailable.", true);
    }

    private static InvalidEvidenceException missingArtifact() {
        return new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_MISSING", "Referenced artifact is missing.");
    }

    private static String requiredConfig(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required artifact-store configuration: " + name + ".");
        }
        return value;
    }

    private static String normalizePrefix(String value) {
        if (value == null || value.isBlank()) return "";
        String normalized = value.replace('\\', '/');
        if (normalized.startsWith("/") || normalized.startsWith("//")) {
            throw new IllegalStateException("Artifact-store prefix must be relative.");
        }
        while (normalized.endsWith("/")) {
            normalized = normalized.substring(0, normalized.length() - 1);
        }
        if (normalized.isBlank()) {
            throw new IllegalStateException("Artifact-store prefix must contain a path segment.");
        }
        for (String segment : normalized.split("/", -1)) {
            if (segment.isBlank() || ".".equals(segment) || "..".equals(segment)) {
                throw new IllegalStateException("Artifact-store prefix contains an unsafe path segment.");
            }
        }
        return normalized + "/";
    }

    private static S3Client buildClient(
            String endpoint,
            String region,
            String accessKey,
            String secretKey,
            boolean pathStyleAccess,
            long connectTimeoutMs,
            long apiTimeoutMs,
            long attemptTimeoutMs
    ) {
        String configuredEndpoint = requiredConfig(endpoint, "RPF_ARTIFACT_STORE_S3_ENDPOINT");
        String configuredRegion = requiredConfig(region, "RPF_ARTIFACT_STORE_S3_REGION");
        String configuredAccess = requiredConfig(accessKey, "RPF_ARTIFACT_STORE_S3_ACCESS_KEY");
        String configuredSecret = requiredConfig(secretKey, "RPF_ARTIFACT_STORE_S3_SECRET_KEY");
        if (connectTimeoutMs < 1 || apiTimeoutMs < 1 || attemptTimeoutMs < 1) {
            throw new IllegalStateException("Artifact-store timeouts must be positive.");
        }
        URI uri;
        try {
            uri = URI.create(configuredEndpoint);
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("Artifact-store endpoint is invalid.", exception);
        }
        if (!"http".equalsIgnoreCase(uri.getScheme()) && !"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalStateException("Artifact-store endpoint must use HTTP or HTTPS.");
        }
        return S3Client.builder()
                .endpointOverride(uri)
                .region(Region.of(configuredRegion))
                .forcePathStyle(pathStyleAccess)
                .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create(configuredAccess, configuredSecret)))
                .httpClientBuilder(UrlConnectionHttpClient.builder())
                .requestChecksumCalculation(RequestChecksumCalculation.WHEN_REQUIRED)
                .responseChecksumValidation(ResponseChecksumValidation.WHEN_REQUIRED)
                .overrideConfiguration(ClientOverrideConfiguration.builder()
                        .apiCallTimeout(Duration.ofMillis(apiTimeoutMs))
                        .apiCallAttemptTimeout(Duration.ofMillis(attemptTimeoutMs))
                        .retryPolicy(RetryPolicy.none())
                        .build())
                .build();
    }

    @PreDestroy
    void close() {
        if (closeClient) client.close();
    }
}
