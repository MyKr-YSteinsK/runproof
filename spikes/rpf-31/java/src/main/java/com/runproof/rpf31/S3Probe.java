package com.runproof.rpf31;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.core.checksums.RequestChecksumCalculation;
import software.amazon.awssdk.core.checksums.ResponseChecksumValidation;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.http.urlconnection.UrlConnectionHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.BucketAlreadyExistsException;
import software.amazon.awssdk.services.s3.model.BucketAlreadyOwnedByYouException;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.GetObjectLockConfigurationRequest;
import software.amazon.awssdk.services.s3.model.GetObjectLockConfigurationResponse;
import software.amazon.awssdk.services.s3.model.GetBucketVersioningRequest;
import software.amazon.awssdk.services.s3.model.GetBucketVersioningResponse;
import software.amazon.awssdk.services.s3.model.HeadBucketRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;
import software.amazon.awssdk.services.s3.model.S3Exception;
import software.amazon.awssdk.services.s3.model.NoSuchBucketException;
import software.amazon.awssdk.core.retry.RetryPolicy;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * Disposable RPF-31 S3-compatible contract probe.
 *
 * The only provider-facing client here is the AWS SDK for Java S3 client.  The
 * probe deliberately never performs a HEAD-before-PUT decision: immutable
 * create is tested through PutObject If-None-Match: * and a losing writer only
 * performs a GET to classify replay versus conflict.
 */
public final class S3Probe {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String CONDITIONAL_HEADER = "*";
    private static final int CONCURRENCY = 8;
    private static final Duration API_TIMEOUT = Duration.ofSeconds(5);
    private static final Duration ATTEMPT_TIMEOUT = Duration.ofSeconds(3);

    private S3Probe() {
    }

    public static void main(String[] args) throws Exception {
        try {
            Arguments arguments = Arguments.parse(args);
            Map<String, Object> result = switch (arguments.mode) {
                case "full" -> runFull(arguments);
                case "restart" -> runRestart(arguments);
                case "unavailable" -> runUnavailable(arguments);
                case "health" -> runHealth(arguments);
                default -> throw new IllegalArgumentException("unsupported mode");
            };
            System.out.println(MAPPER.writeValueAsString(result));
        } catch (Throwable error) {
            Map<String, Object> failure = ordered("status", "FAIL", "error_type", error.getClass().getSimpleName());
            if (error instanceof S3Exception s3) {
                failure.put("error", errorSummary(s3));
            }
            String message = safeMessage(error.getMessage());
            if (!message.isBlank()) {
                failure.put("error_message", message);
            }
            failure.put("cause_types", causeTypes(error));
            System.out.println(MAPPER.writeValueAsString(failure));
            System.exit(1);
        }
    }

    private static Map<String, Object> runFull(Arguments a) {
        require(!a.bucket.isBlank(), "bucket is required");
        require(!a.prefix.isBlank(), "prefix is required");
        String step = "start";
        try (S3Client client = client(a.endpoint, a.accessKey, a.secretKey)) {
            step = "create_bucket";
            createBucket(client, a.bucket);
            String runId = a.prefix.replace('/', '-');
            String entityId = "rpf31-entity-" + runId;
            String sourceSha = sha256("rpf31-source-v1".getBytes(StandardCharsets.UTF_8));
            String runtimeVersion = "rpf31-java-s3-probe-v1";
            byte[] payloadA = jsonPayload(entityId, sourceSha, runtimeVersion, "A");
            byte[] payloadB = jsonPayload(entityId, sourceSha, runtimeVersion, "B");
            Expected expected = new Expected(sha256(payloadA), entityId, sourceSha, runtimeVersion);

            String primaryKey = a.prefix + "primary.json";
            step = "first_put";
            Map<String, Object> first = putIfAbsent(client, a.bucket, primaryKey, payloadA, metadata(expected));
            require("CREATED".equals(first.get("state")), "first put did not create");
            step = "same_content_replay";
            Map<String, Object> replay = putIfAbsent(client, a.bucket, primaryKey, payloadA, metadata(expected));
            require("IDEMPOTENT".equals(replay.get("state")), "same-content replay was not idempotent");
            step = "different_content_conflict";
            Map<String, Object> conflict = putIfAbsent(client, a.bucket, primaryKey, payloadB, metadata(expected));
            require("CONFLICT".equals(conflict.get("state")), "different-content replay was not conflict");
            step = "verified_read";
            Map<String, Object> verified = readVerified(client, a.bucket, primaryKey, expected);
            require("VERIFIED".equals(verified.get("status")), "primary verified read failed");

            step = "concurrent_same_content";
            Map<String, Object> concurrentSame = concurrentSame(client, a.bucket, a.prefix + "concurrent-same.bin", payloadA);
            step = "concurrent_different_content";
            Map<String, Object> concurrentDifferent = concurrentDifferent(client, a.bucket, a.prefix + "concurrent-different.bin", payloadA, payloadB);
            boolean racesPassed = Boolean.TRUE.equals(concurrentSame.get("passed")) && Boolean.TRUE.equals(concurrentDifferent.get("passed"));

            String missingKey = a.prefix + "missing.json";
            step = "missing_object";
            Map<String, Object> missing = readVerified(client, a.bucket, missingKey, expected);
            require("MISSING".equals(missing.get("status")), "missing object was not fail-closed");

            String corruptKey = a.prefix + "corrupt.json";
            step = "corrupt_original_put";
            putIfAbsent(client, a.bucket, corruptKey, payloadA, metadata(expected));
            byte[] corruptedBytes = "corrupted!!".getBytes(StandardCharsets.UTF_8);
            step = "corrupt_admin_overwrite";
            client.putObject(PutObjectRequest.builder().bucket(a.bucket).key(corruptKey).contentLength((long) corruptedBytes.length).build(), RequestBody.fromBytes(corruptedBytes));
            step = "corrupt_verified_read";
            Map<String, Object> corrupt = readVerified(client, a.bucket, corruptKey, expected);
            require("HASH_MISMATCH".equals(corrupt.get("status")), "corrupt object was not rejected");

            String identityKey = a.prefix + "wrong-identity.json";
            step = "wrong_identity";
            Expected identityExpected = new Expected(sha256(payloadB), entityId + "-expected", sourceSha, runtimeVersion);
            putIfAbsent(client, a.bucket, identityKey, payloadB, metadata(identityExpected));
            Map<String, Object> wrongIdentity = readVerified(client, a.bucket, identityKey, identityExpected);
            require("IDENTITY_MISMATCH".equals(wrongIdentity.get("status")), "wrong identity was not rejected");

            step = "credential_policy";
            Map<String, Object> credentials = credentialChecks(a, primaryKey, expected);
            boolean credentialBoundaryPassed = Boolean.TRUE.equals(credentials.get("wrong_credential_rejected"))
                && (!Boolean.TRUE.equals(credentials.get("configured_read_only"))
                    || (Boolean.TRUE.equals(credentials.get("read_only_put_rejected")) && Boolean.TRUE.equals(credentials.get("read_only_get_allowed"))));

            step = "size_probe";
            Map<String, Object> sizes = sizeProbe(client, a.bucket, a.prefix);
            step = "orphan_replay";
            Map<String, Object> orphan = orphanProbe(client, a.bucket, a.prefix, payloadA, payloadB, expected);
            require(Boolean.TRUE.equals(orphan.get("safe_replay")), "orphan replay was not safe");
            step = "response_lost_replay";
            Map<String, Object> responseLost = responseLostReplay(client, a.bucket, a.prefix, payloadA, expected);
            require(Boolean.TRUE.equals(responseLost.get("safe_replay")), "response-lost replay was not safe");
            Map<String, Object> persistence = persistenceMetadata(client, a.bucket);
            String responseEtag = String.valueOf(first.get("etag"));
            String normalizedEtag = responseEtag.replace("\"", "");
            Map<String, Object> etag = ordered(
                "response_etag", responseEtag,
                "normalized_etag", normalizedEtag,
                "md5_of_payload", md5(payloadA),
                "etag_equals_md5_observation", Objects.equals(normalizedEtag, md5(payloadA)),
                "canonical_integrity", "RunProof SHA-256 computed from GET bytes; ETag is not trusted"
            );

            return ordered(
                "status", racesPassed && credentialBoundaryPassed ? "PASS" : "FAIL",
                "candidate_status", racesPassed && credentialBoundaryPassed ? "CORE_PASS" : "CONTRACT_BOUNDARY_FAILED",
                "contract_passed", racesPassed && credentialBoundaryPassed,
                "bucket", a.bucket,
                "prefix", a.prefix,
                "primary", ordered(
                    "key", primaryKey,
                    "expected_sha256", expected.sha256,
                    "entity_id", expected.entityId,
                    "source_sha256", expected.sourceSha,
                    "runtime_version", expected.runtimeVersion,
                    "size", payloadA.length
                ),
                "first_put", first,
                "same_content_replay", replay,
                "different_content_conflict", conflict,
                "verified_read", verified,
                "concurrent_same_content", concurrentSame,
                "concurrent_different_content", concurrentDifferent,
                "missing_object", missing,
                "corrupt_object", corrupt,
                "wrong_identity", wrongIdentity,
                "credential_policy", credentials,
                "size_probe", sizes,
                "orphan_put_before_metadata", orphan,
                "metadata_before_ack_response_lost", responseLost,
                "etag_checksum", etag,
                "persistence_features", persistence,
                "conditional_write", "PutObject If-None-Match: *; no HEAD-before-PUT fallback",
                "physical_key", "stable artifact key under a RunProof-owned prefix; content-addressed key not required for atomicity",
                "delete_semantics", "ArtifactStore v1 has no general delete; disposable cleanup is external",
                "versioning_object_lock", "investigated as optional metadata only; application-level immutability does not depend on either"
            );
        } catch (S3Exception error) {
            return ordered("status", "FAIL", "error_type", error.getClass().getSimpleName(), "error", errorSummary(error), "error_message", safeMessage(error.getMessage()), "cause_types", causeTypes(error), "step", step);
        }
    }

    private static Map<String, Object> runRestart(Arguments a) {
        try (S3Client client = client(a.endpoint, a.accessKey, a.secretKey)) {
            Expected expected = new Expected(a.expectedSha, a.entityId, a.sourceSha, a.runtimeVersion);
            Map<String, Object> verified = readVerified(client, a.bucket, a.key, expected);
            Map<String, Object> replay = putIfAbsent(client, a.bucket, a.key, jsonPayload(a.entityId, a.sourceSha, a.runtimeVersion, "A"), metadata(expected));
            require("VERIFIED".equals(verified.get("status")), "restart read failed");
            require("IDEMPOTENT".equals(replay.get("state")), "restart replay failed");
            return ordered("status", "PASS", "read_after_restart", verified, "replay_after_restart", replay, "bytes_and_hash_preserved", true);
        }
    }

    private static Map<String, Object> runUnavailable(Arguments a) {
        try (S3Client client = client(a.endpoint, a.accessKey, a.secretKey)) {
            Map<String, Object> health = health(client, a.bucket);
            Map<String, Object> read = readVerified(client, a.bucket, a.key, new Expected(a.expectedSha, a.entityId, a.sourceSha, a.runtimeVersion));
            boolean unavailable = !Boolean.TRUE.equals(health.get("available")) && !"VERIFIED".equals(read.get("status"));
            require(unavailable, "stopped endpoint unexpectedly behaved as available");
            return ordered("status", "PASS", "available", false, "health", health, "read", read, "agent_outcome_unchanged", true, "storage_error_class", "PLATFORM_STORAGE_UNAVAILABLE");
        }
    }

    private static Map<String, Object> runHealth(Arguments a) {
        try (S3Client client = client(a.endpoint, a.accessKey, a.secretKey)) {
            Map<String, Object> health = health(client, a.bucket);
            return ordered("status", "PASS", "health", health);
        }
    }

    private static S3Client client(String endpoint, String accessKey, String secretKey) {
        require(!endpoint.isBlank(), "endpoint is required");
        require(!accessKey.isBlank() && !secretKey.isBlank(), "credentials are required");
        return S3Client.builder()
            .endpointOverride(URI.create(endpoint))
            .region(Region.of("us-east-1"))
            .forcePathStyle(true)
            .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create(accessKey, secretKey)))
            .httpClientBuilder(UrlConnectionHttpClient.builder())
            .requestChecksumCalculation(RequestChecksumCalculation.WHEN_REQUIRED)
            .responseChecksumValidation(ResponseChecksumValidation.WHEN_REQUIRED)
            .overrideConfiguration(ClientOverrideConfiguration.builder()
                .apiCallTimeout(API_TIMEOUT)
                .apiCallAttemptTimeout(ATTEMPT_TIMEOUT)
                .retryPolicy(RetryPolicy.none())
                .build())
            .build();
    }

    private static void createBucket(S3Client client, String bucket) {
        try {
            client.createBucket(CreateBucketRequest.builder().bucket(bucket).build());
        } catch (BucketAlreadyOwnedByYouException | BucketAlreadyExistsException ignored) {
            // Disposable bucket names are unique; this is only an idempotent bootstrap guard.
        }
    }

    private static Map<String, Object> putIfAbsent(S3Client client, String bucket, String key, byte[] content, Map<String, String> metadata) {
        String contentSha = sha256(content);
        try {
            PutObjectResponse response = client.putObject(
                PutObjectRequest.builder()
                    .bucket(bucket).key(key).ifNoneMatch(CONDITIONAL_HEADER)
                    .contentLength((long) content.length).contentType("application/octet-stream")
                    .metadata(metadata).build(),
                RequestBody.fromBytes(content)
            );
            return ordered("state", "CREATED", "content_sha256", contentSha, "size", content.length, "etag", response.eTag());
        } catch (S3Exception error) {
            int status = error.statusCode();
            if (status != 409 && status != 412 && !isPrecondition(error)) {
                throw error;
            }
            byte[] existing = readRawWithRetry(client, bucket, key);
            boolean same = Arrays.equals(existing, content);
            return ordered(
                "state", same ? "IDEMPOTENT" : "CONFLICT",
                "content_sha256", contentSha,
                "stored_sha256", sha256(existing),
                "size", existing.length,
                "conditional_failure", errorSummary(error)
            );
        }
    }

    private static boolean isPrecondition(S3Exception error) {
        if (error.awsErrorDetails() == null) {
            return false;
        }
        String code = error.awsErrorDetails().errorCode();
        return "PreconditionFailed".equalsIgnoreCase(code) || "ConditionalRequestConflict".equalsIgnoreCase(code);
    }

    private static byte[] readRawWithRetry(S3Client client, String bucket, String key) {
        S3Exception last = null;
        for (int attempt = 0; attempt < 12; attempt++) {
            try {
                return readRaw(client, bucket, key);
            } catch (S3Exception error) {
                last = error;
                try {
                    Thread.sleep(80L * (attempt + 1));
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw error;
                }
            }
        }
        throw last == null ? new IllegalStateException("conditional write loser could not read object") : last;
    }

    private static byte[] readRaw(S3Client client, String bucket, String key) {
        ResponseBytes<GetObjectResponse> response = client.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(key).build());
        return response.asByteArray();
    }

    private static Map<String, Object> readVerified(S3Client client, String bucket, String key, Expected expected) {
        try {
            byte[] bytes = readRaw(client, bucket, key);
            String actualSha = sha256(bytes);
            if (!actualSha.equals(expected.sha256)) {
                return ordered("status", "HASH_MISMATCH", "key", key, "expected_sha256", expected.sha256, "actual_sha256", actualSha, "bytes", bytes.length);
            }
            JsonNode document;
            try {
                document = MAPPER.readTree(bytes);
            } catch (Exception parseError) {
                return ordered("status", "PARSE_MISMATCH", "key", key, "sha256", actualSha);
            }
            if (!expected.entityId.equals(document.path("entity_id").asText())
                || !expected.sourceSha.equals(document.path("source_sha256").asText())
                || !expected.runtimeVersion.equals(document.path("runtime_version").asText())
                || !"rpf-evidence-v1".equals(document.path("schema_version").asText())) {
                return ordered("status", "IDENTITY_MISMATCH", "key", key, "sha256", actualSha);
            }
            return ordered("status", "VERIFIED", "key", key, "sha256", actualSha, "bytes", bytes.length, "read_mode", "one GET body -> SHA-256 -> parse -> identity verification");
        } catch (S3Exception error) {
            if (error.statusCode() == 404 || "NoSuchKey".equalsIgnoreCase(errorCode(error)) || "NoSuchBucket".equalsIgnoreCase(errorCode(error))) {
                return ordered("status", "MISSING", "key", key, "error", errorSummary(error), "fail_closed", true);
            }
            return ordered("status", "BACKEND_ERROR", "key", key, "error", errorSummary(error), "fail_closed", true, "storage_error_class", "PLATFORM_STORAGE_ERROR");
        } catch (Exception error) {
            return ordered("status", "BACKEND_ERROR", "key", key, "error_type", error.getClass().getSimpleName(), "error_message", safeMessage(error.getMessage()), "fail_closed", true, "storage_error_class", "PLATFORM_STORAGE_ERROR");
        }
    }

    private static Map<String, Object> concurrentSame(S3Client client, String bucket, String key, byte[] content) {
        List<Map<String, Object>> results = parallel(CONCURRENCY, () -> putIfAbsent(client, bucket, key, content, Map.of("rpf-sha256", sha256(content))));
        long created = results.stream().filter(item -> "CREATED".equals(item.get("state"))).count();
        long idempotent = results.stream().filter(item -> "IDEMPOTENT".equals(item.get("state"))).count();
        long failed = results.stream().filter(item -> "FAILED".equals(item.get("state"))).count();
        return ordered("writers", CONCURRENCY, "created", created, "idempotent", idempotent, "conflict", results.stream().filter(item -> "CONFLICT".equals(item.get("state"))).count(), "failed", failed, "failures", results.stream().filter(item -> "FAILED".equals(item.get("state"))).toList(), "passed", created == 1 && idempotent == CONCURRENCY - 1 && failed == 0);
    }

    private static Map<String, Object> concurrentDifferent(S3Client client, String bucket, String key, byte[] a, byte[] b) {
        List<Map<String, Object>> results = new ArrayList<>();
        ExecutorService executor = Executors.newFixedThreadPool(CONCURRENCY);
        try {
            List<Future<Map<String, Object>>> futures = new ArrayList<>();
            for (int index = 0; index < CONCURRENCY; index++) {
                byte[] content = index % 2 == 0 ? a : b;
                futures.add(executor.submit(() -> putIfAbsent(client, bucket, key, content, Map.of("rpf-sha256", sha256(content)))));
            }
            for (Future<Map<String, Object>> future : futures) {
                try {
                    results.add(future.get());
                } catch (Exception error) {
                    results.add(ordered("state", "FAILED", "error_type", error.getClass().getSimpleName(), "error_message", safeMessage(error.getMessage()), "cause_types", causeTypes(error)));
                }
            }
        } finally {
            executor.shutdownNow();
        }
        long created = results.stream().filter(item -> "CREATED".equals(item.get("state"))).count();
        long conflicts = results.stream().filter(item -> "CONFLICT".equals(item.get("state"))).count();
        long idempotent = results.stream().filter(item -> "IDEMPOTENT".equals(item.get("state"))).count();
        long failed = results.stream().filter(item -> "FAILED".equals(item.get("state"))).count();
        return ordered("writers", CONCURRENCY, "created", created, "conflict", conflicts, "idempotent", idempotent, "failed", failed, "failures", results.stream().filter(item -> "FAILED".equals(item.get("state"))).toList(), "passed", created == 1 && conflicts >= 1 && failed == 0 && conflicts + idempotent == CONCURRENCY - 1, "interpretation", "one winner; same-byte duplicate losers may be idempotent and different-byte losers must conflict");
    }

    private static List<Map<String, Object>> parallel(int count, Callable<Map<String, Object>> callable) {
        ExecutorService executor = Executors.newFixedThreadPool(count);
        try {
            List<Future<Map<String, Object>>> futures = new ArrayList<>();
            for (int index = 0; index < count; index++) {
                futures.add(executor.submit(callable));
            }
            List<Map<String, Object>> results = new ArrayList<>();
            for (Future<Map<String, Object>> future : futures) {
                try {
                    results.add(future.get());
                } catch (Exception error) {
                    results.add(ordered("state", "FAILED", "error_type", error.getClass().getSimpleName(), "error_message", safeMessage(error.getMessage()), "cause_types", causeTypes(error)));
                }
            }
            return results;
        } finally {
            executor.shutdownNow();
        }
    }

    private static Map<String, Object> credentialChecks(Arguments a, String key, Expected expected) {
        boolean configured = !a.readOnlyAccess.isBlank() && !a.readOnlySecret.isBlank();
        Map<String, Object> result = ordered("configured_read_only", configured, "scope", "single bucket/prefix disposable identity");
        try (S3Client wrong = client(a.endpoint, a.wrongAccess, a.wrongSecret)) {
            Map<String, Object> wrongRead = readVerified(wrong, a.bucket, key, new Expected(a.expectedSha, a.entityId, a.sourceSha, a.runtimeVersion));
            result.put("wrong_credential_rejected", !"VERIFIED".equals(wrongRead.get("status")));
            result.put("wrong_credential", wrongRead);
        } catch (Exception error) {
            result.put("wrong_credential_rejected", true);
            result.put("wrong_credential", ordered("status", "DENIED", "error_type", error.getClass().getSimpleName()));
        }
        if (!configured) {
            result.put("read_only_get_allowed", false);
            result.put("read_only_put_rejected", false);
            result.put("read_only_status", "NOT_CONFIGURED_FOR_CANDIDATE");
            return result;
        }
        try (S3Client readOnly = client(a.endpoint, a.readOnlyAccess, a.readOnlySecret)) {
            Map<String, Object> read = readVerified(readOnly, a.bucket, key, expected);
            result.put("read_only_get_allowed", "VERIFIED".equals(read.get("status")));
            result.put("read_only_get", read);
            try {
                readOnly.putObject(PutObjectRequest.builder().bucket(a.bucket).key(a.prefix + "read-only-must-fail").ifNoneMatch("*").build(), RequestBody.fromBytes("denied".getBytes(StandardCharsets.UTF_8)));
                result.put("read_only_put_rejected", false);
                result.put("read_only_put", ordered("status", "UNEXPECTED_SUCCESS"));
            } catch (S3Exception denied) {
                result.put("read_only_put_rejected", true);
                result.put("read_only_put", ordered("status", "DENIED", "error", errorSummary(denied)));
            }
        } catch (Exception error) {
            result.put("read_only_get_allowed", false);
            result.put("read_only_put_rejected", true);
            result.put("read_only_status", "READ_FAILED");
            result.put("read_only_error_type", error.getClass().getSimpleName());
        }
        return result;
    }

    private static Map<String, Object> sizeProbe(S3Client client, String bucket, String prefix) {
        List<Map<String, Object>> measurements = new ArrayList<>();
        for (int size : List.of(1024, 1024 * 1024, 16 * 1024 * 1024)) {
            byte[] content = new byte[size];
            for (int index = 0; index < content.length; index++) {
                content[index] = (byte) (index * 31 + 7);
            }
            String key = prefix + "size-" + size + ".bin";
            long before = usedMemory();
            long started = System.nanoTime();
            Map<String, Object> put = putIfAbsent(client, bucket, key, content, Map.of("rpf-size", Integer.toString(size)));
            long putMs = elapsedMs(started);
            started = System.nanoTime();
            byte[] read = readRaw(client, bucket, key);
            long getMs = elapsedMs(started);
            long after = usedMemory();
            require(Arrays.equals(content, read), "size probe bytes changed");
            measurements.add(ordered("bytes", size, "put_state", put.get("state"), "put_ms", putMs, "get_verify_ms", getMs, "memory_delta_bytes_directional", Math.max(0L, after - before), "sha256", sha256(read)));
        }
        return ordered("measurement", "directional local process timing, not a capacity benchmark", "cases", measurements);
    }

    private static Map<String, Object> orphanProbe(S3Client client, String bucket, String prefix, byte[] a, byte[] b, Expected expected) {
        String key = prefix + "orphan.json";
        Map<String, Object> put = putIfAbsent(client, bucket, key, a, metadata(expected));
        Map<String, Object> replay = putIfAbsent(client, bucket, key, a, metadata(expected));
        Map<String, Object> conflict = putIfAbsent(client, bucket, key, b, metadata(expected));
        return ordered("object_put", put, "canonical_metadata_written", false, "orphan_is_not_canonical", true, "same_bytes_replay", replay, "different_bytes_conflict", conflict, "safe_replay", "IDEMPOTENT".equals(replay.get("state")) && "CONFLICT".equals(conflict.get("state")), "future_gc", "separate retention/GC decision; not implemented in v1");
    }

    private static Map<String, Object> responseLostReplay(S3Client client, String bucket, String prefix, byte[] a, Expected expected) {
        String key = prefix + "response-lost.json";
        Map<String, Object> first = putIfAbsent(client, bucket, key, a, metadata(expected));
        boolean metadataCommitSimulated = "CREATED".equals(first.get("state"));
        Map<String, Object> replay = putIfAbsent(client, bucket, key, a, metadata(expected));
        return ordered("first_put", first, "metadata_commit_simulated", metadataCommitSimulated, "client_ack_received", false, "replay", replay, "safe_replay", "IDEMPOTENT".equals(replay.get("state")), "second_canonical_object", false);
    }

    private static Map<String, Object> persistenceMetadata(S3Client client, String bucket) {
        Map<String, Object> result = new LinkedHashMap<>();
        try {
            GetBucketVersioningResponse versioning = client.getBucketVersioning(GetBucketVersioningRequest.builder().bucket(bucket).build());
            result.put("versioning", versioning.statusAsString());
        } catch (Exception error) {
            result.put("versioning", ordered("status", "UNAVAILABLE_OR_UNSUPPORTED", "error_type", error.getClass().getSimpleName()));
        }
        try {
            GetObjectLockConfigurationResponse lock = client.getObjectLockConfiguration(GetObjectLockConfigurationRequest.builder().bucket(bucket).build());
            result.put("object_lock", lock.objectLockConfiguration() == null
                ? "NOT_CONFIGURED"
                : lock.objectLockConfiguration().objectLockEnabledAsString());
        } catch (NoSuchBucketException error) {
            result.put("object_lock", ordered("status", "NOT_CONFIGURED"));
        } catch (Exception error) {
            result.put("object_lock", ordered("status", "UNAVAILABLE_OR_UNSUPPORTED", "error_type", error.getClass().getSimpleName()));
        }
        result.put("application_immutability_required", true);
        result.put("versioning_required", false);
        result.put("object_lock_required", false);
        return result;
    }

    private static Map<String, Object> health(S3Client client, String bucket) {
        try {
            client.headBucket(HeadBucketRequest.builder().bucket(bucket).build());
            return ordered("available", true, "operation", "HEAD bucket");
        } catch (S3Exception error) {
            return ordered("available", false, "operation", "HEAD bucket", "error", errorSummary(error));
        } catch (Exception error) {
            return ordered("available", false, "operation", "HEAD bucket", "error_type", error.getClass().getSimpleName());
        }
    }

    private static Map<String, String> metadata(Expected expected) {
        return Map.of(
            "rpf-sha256", expected.sha256,
            "rpf-schema", "rpf-evidence-v1",
            "rpf-entity", expected.entityId,
            "rpf-source", expected.sourceSha
        );
    }

    private static byte[] jsonPayload(String entityId, String sourceSha, String runtimeVersion, String marker) {
        ObjectNode node = MAPPER.createObjectNode();
        node.put("artifact_kind", "RPF-31-Probe-Evidence");
        node.put("schema_version", "rpf-evidence-v1");
        node.put("entity_id", entityId);
        node.put("source_sha256", sourceSha);
        node.put("runtime_version", runtimeVersion);
        node.put("marker", marker);
        try {
            return MAPPER.writeValueAsBytes(node);
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static Map<String, Object> errorSummary(S3Exception error) {
        return ordered("type", error.getClass().getSimpleName(), "status", error.statusCode(), "code", errorCode(error));
    }

    private static String errorCode(S3Exception error) {
        return error.awsErrorDetails() == null || error.awsErrorDetails().errorCode() == null ? "UNKNOWN_S3_ERROR" : error.awsErrorDetails().errorCode();
    }

    private static String safeMessage(String message) {
        if (message == null || message.isBlank() || message.matches("(?i).*secret|credential|token|password.*")) {
            return "";
        }
        return message.length() > 240 ? message.substring(0, 240) : message;
    }

    private static List<String> causeTypes(Throwable error) {
        List<String> types = new ArrayList<>();
        Throwable current = error;
        while (current != null && types.size() < 6) {
            types.add(current.getClass().getSimpleName());
            current = current.getCause();
        }
        return types;
    }

    private static long usedMemory() {
        Runtime runtime = Runtime.getRuntime();
        return runtime.totalMemory() - runtime.freeMemory();
    }

    private static long elapsedMs(long started) {
        return Math.max(0L, (System.nanoTime() - started) / 1_000_000L);
    }

    private static String sha256(byte[] bytes) {
        return digest("SHA-256", bytes);
    }

    private static String md5(byte[] bytes) {
        return digest("MD5", bytes);
    }

    private static String digest(String algorithm, byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance(algorithm).digest(bytes);
            StringBuilder builder = new StringBuilder(digest.length * 2);
            for (byte value : digest) {
                builder.append(String.format("%02x", value));
            }
            return builder.toString();
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static Map<String, Object> ordered(Object... values) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int index = 0; index + 1 < values.length; index += 2) {
            result.put(String.valueOf(values[index]), values[index + 1]);
        }
        return result;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private record Expected(String sha256, String entityId, String sourceSha, String runtimeVersion) {
    }

    private static final class Arguments {
        private final String mode;
        private final String endpoint;
        private final String bucket;
        private final String prefix;
        private final String key;
        private final String expectedSha;
        private final String entityId;
        private final String sourceSha;
        private final String runtimeVersion;
        private final String accessKey;
        private final String secretKey;
        private final String readOnlyAccess;
        private final String readOnlySecret;
        private final String wrongAccess;
        private final String wrongSecret;

        private Arguments(Map<String, String> values) {
            mode = values.getOrDefault("mode", "full");
            endpoint = values.getOrDefault("endpoint", "");
            bucket = values.getOrDefault("bucket", "");
            prefix = values.getOrDefault("prefix", "");
            key = values.getOrDefault("key", "");
            expectedSha = values.getOrDefault("expected-sha", "");
            entityId = values.getOrDefault("entity-id", "");
            sourceSha = values.getOrDefault("source-sha", "");
            runtimeVersion = values.getOrDefault("runtime-version", "rpf31-java-s3-probe-v1");
            accessKey = envOr(values, "access-key", "RPF31_ACCESS_KEY");
            secretKey = envOr(values, "secret-key", "RPF31_SECRET_KEY");
            readOnlyAccess = envOr(values, "readonly-access", "RPF31_READONLY_ACCESS");
            readOnlySecret = envOr(values, "readonly-secret", "RPF31_READONLY_SECRET");
            wrongAccess = envOr(values, "wrong-access", "RPF31_WRONG_ACCESS");
            wrongSecret = envOr(values, "wrong-secret", "RPF31_WRONG_SECRET");
        }

        private static String envOr(Map<String, String> values, String key, String env) {
            String direct = values.get(key);
            if (direct != null) {
                return direct;
            }
            return System.getenv().getOrDefault(env, "");
        }

        private static Arguments parse(String[] args) {
            Map<String, String> values = new LinkedHashMap<>();
            for (String arg : args) {
                if (!arg.startsWith("--") || !arg.contains("=")) {
                    throw new IllegalArgumentException("arguments must use --name=value");
                }
                int separator = arg.indexOf('=');
                values.put(arg.substring(2, separator), arg.substring(separator + 1));
            }
            return new Arguments(values);
        }
    }
}
