package com.runproof.rpf33;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.core.checksums.RequestChecksumCalculation;
import software.amazon.awssdk.core.checksums.ResponseChecksumValidation;
import software.amazon.awssdk.core.retry.RetryPolicy;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.http.urlconnection.UrlConnectionHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;

import java.io.BufferedWriter;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * Disposable RPF-33 S3 fixture and directional measurement helper.
 *
 * This class is deliberately outside the formal Control Plane. It uses the
 * same AWS SDK version and endpoint shape as RPF-32, but only creates objects
 * under the probe-owned prefix and emits a redacted CSV manifest.
 */
public final class BulkS3Probe {

    private static final Map<String, Contract> CONTRACTS = contracts();

    private BulkS3Probe() {
    }

    public static void main(String[] args) throws Exception {
        try {
            Map<String, String> values = parse(args);
            String mode = values.getOrDefault("mode", "seed");
            String endpoint = required(values.get("endpoint"), "endpoint");
            String bucket = required(values.get("bucket"), "bucket");
            String prefix = normalizePrefix(values.getOrDefault("prefix", ""));
            String access = required(System.getenv("RPF33_ACCESS_KEY"), "RPF33_ACCESS_KEY");
            String secret = required(System.getenv("RPF33_SECRET_KEY"), "RPF33_SECRET_KEY");
            try (S3Client client = client(endpoint, access, secret)) {
                Map<String, Object> result = switch (mode) {
                    case "seed" -> seed(client, bucket, prefix, values);
                    case "sample" -> sample(client, bucket, prefix, values);
                    case "count" -> count(client, bucket, prefix);
                    case "orphan" -> orphan(client, bucket, prefix, values);
                    default -> throw new IllegalArgumentException("unsupported mode");
                };
                System.out.println(toJson(result));
            }
        } catch (Throwable error) {
            Map<String, Object> failure = new LinkedHashMap<>();
            failure.put("status", "FAIL");
            failure.put("error_type", error.getClass().getSimpleName());
            failure.put("error_code", error.getMessage() == null ? "UNSPECIFIED" : safeCode(error.getMessage()));
            System.out.println(toJson(failure));
            System.exit(1);
        }
    }

    private static Map<String, Object> seed(S3Client client, String bucket, String prefix, Map<String, String> values) throws Exception {
        String runtime = required(values.get("runtime-version"), "runtime-version");
        String source = required(values.get("source-sha256"), "source-sha256");
        String types = required(values.get("types"), "types");
        int threads = boundedInt(values.getOrDefault("threads", "8"), 1, 16, "threads");
        int timelineEvents = boundedInt(values.getOrDefault("timeline-events", "0"), 0, 100_000, "timeline-events");
        Path manifestPath = Path.of(required(values.get("manifest-out"), "manifest-out"));
        List<WorkItem> work = new ArrayList<>();
        for (String part : types.split(",")) {
            String[] pieces = part.split(":", -1);
            if (pieces.length != 2 || !CONTRACTS.containsKey(pieces[0])) throw new IllegalArgumentException("invalid types");
            String range = pieces[1];
            String[] bounds = range.split("-", -1);
            int first = 1;
            int last;
            if (bounds.length == 1) {
                last = boundedInt(bounds[0], 0, 100_000, "type count");
            } else if (bounds.length == 2) {
                first = boundedInt(bounds[0], 1, 100_000, "type range start");
                last = boundedInt(bounds[1], first, 100_000, "type range end");
            } else {
                throw new IllegalArgumentException("invalid type range");
            }
            for (int index = first; index <= last; index++) {
                work.add(new WorkItem(pieces[0], index, index == 1 && "RUN".equals(pieces[0]) ? timelineEvents : 0));
            }
        }
        long started = System.nanoTime();
        ExecutorService executor = Executors.newFixedThreadPool(threads);
        List<Future<Entry>> futures = new ArrayList<>();
        for (WorkItem item : work) {
            futures.add(executor.submit(new PutTask(client, bucket, prefix, item, source, runtime)));
        }
        List<Entry> entries = new ArrayList<>(work.size());
        try {
            for (Future<Entry> future : futures) entries.add(future.get());
        } catch (ExecutionException error) {
            throw new IllegalStateException("S3 fixture put failed", error.getCause());
        } finally {
            executor.shutdownNow();
        }
        entries.sort(Comparator.comparing(Entry::entityType).thenComparing(Entry::entityId));
        writeManifest(manifestPath, entries);
        long bytes = entries.stream().mapToLong(Entry::bytes).sum();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "PASS");
        result.put("mode", "seed");
        result.put("objects", entries.size());
        result.put("bytes", bytes);
        result.put("threads", threads);
        result.put("elapsed_ms", elapsedMillis(started));
        result.put("manifest", manifestPath.toString());
        result.put("timeline_events", timelineEvents);
        return result;
    }

    private static Map<String, Object> sample(S3Client client, String bucket, String prefix, Map<String, String> values) {
        String samplePrefix = values.getOrDefault("sample-prefix", "rpf33-sample");
        String sizesValue = values.getOrDefault("sizes", "1024,1048576,16777216");
        List<Map<String, Object>> samples = new ArrayList<>();
        for (String part : sizesValue.split(",")) {
            int size = boundedInt(part, 1, 64 * 1024 * 1024, "sample size");
            byte[] bytes = deterministicBytes(size, size);
            String logicalKey = samplePrefix + "/" + size + ".bin";
            long putStarted = System.nanoTime();
            put(client, bucket, prefix + logicalKey, bytes);
            long putMillis = elapsedMillis(putStarted);
            long getStarted = System.nanoTime();
            ResponseBytes<?> response = client.getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(prefix + logicalKey).build());
            byte[] received = response.asByteArray();
            long getMillis = elapsedMillis(getStarted);
            if (!MessageDigest.isEqual(bytes, received)) throw new IllegalStateException("sample hash mismatch");
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("size_bytes", size);
            item.put("put_ms", putMillis);
            item.put("get_ms", getMillis);
            item.put("sha256", sha256(received));
            samples.add(item);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "PASS");
        result.put("mode", "sample");
        result.put("samples", samples);
        return result;
    }

    private static Map<String, Object> count(S3Client client, String bucket, String prefix) {
        int objects = 0;
        long bytes = 0;
        String token = null;
        int pages = 0;
        do {
            var request = ListObjectsV2Request.builder().bucket(bucket).prefix(prefix);
            if (token != null) request.continuationToken(token);
            var response = client.listObjectsV2(request.build());
            pages++;
            for (var item : response.contents()) {
                objects++;
                bytes += item.size();
            }
            token = response.nextContinuationToken();
        } while (token != null && !token.isBlank());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "PASS");
        result.put("mode", "count");
        result.put("objects", objects);
        result.put("bytes", bytes);
        result.put("pages", pages);
        return result;
    }

    private static Map<String, Object> orphan(S3Client client, String bucket, String prefix, Map<String, String> values) {
        int count = boundedInt(required(values.get("count"), "count"), 0, 100_000, "count");
        int size = boundedInt(values.getOrDefault("size", "256"), 1, 1_048_576, "size");
        String orphanPrefix = values.getOrDefault("orphan-prefix", "orphan");
        long started = System.nanoTime();
        byte[] content = deterministicBytes(size, 33);
        for (int index = 1; index <= count; index++) {
            put(client, bucket, prefix + orphanPrefix + "/" + String.format(Locale.ROOT, "%05d.bin", index), content);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "PASS");
        result.put("mode", "orphan");
        result.put("objects", count);
        result.put("bytes", (long) count * size);
        result.put("elapsed_ms", elapsedMillis(started));
        return result;
    }

    private static final class PutTask implements Callable<Entry> {
        private final S3Client client;
        private final String bucket;
        private final String prefix;
        private final WorkItem item;
        private final String source;
        private final String runtime;

        private PutTask(S3Client client, String bucket, String prefix, WorkItem item, String source, String runtime) {
            this.client = client;
            this.bucket = bucket;
            this.prefix = prefix;
            this.item = item;
            this.source = source;
            this.runtime = runtime;
        }

        @Override
        public Entry call() {
            Contract contract = CONTRACTS.get(item.entityType());
            String entityId = String.format(Locale.ROOT, "rpf33-%s-%05d", item.entityType().toLowerCase(Locale.ROOT), item.index());
            byte[] content = document(contract, entityId, source, runtime, item.timelineEvents());
            String hash = sha256(content);
            String logicalKey = item.entityType().toLowerCase(Locale.ROOT) + "/" + entityId + "/" + hash + ".json";
            put(client, bucket, prefix + logicalKey, content);
            return new Entry(item.entityType(), entityId, logicalKey, contract.schemaVersion(), contract.artifactKind(), hash, source, runtime, content.length, item.timelineEvents());
        }
    }

    private static void put(S3Client client, String bucket, String key, byte[] content) {
        try {
            client.putObject(PutObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .ifNoneMatch("*")
                    .contentLength((long) content.length)
                    .contentType("application/json")
                    .build(), RequestBody.fromBytes(content));
        } catch (S3Exception error) {
            if (error.statusCode() == 412 || error.statusCode() == 409) return;
            throw error;
        }
    }

    private static byte[] document(Contract contract, String entityId, String source, String runtime, int timelineEvents) {
        StringBuilder json = new StringBuilder(Math.max(256, timelineEvents * 80));
        json.append("{\"artifact_kind\":\"").append(escape(contract.artifactKind()))
                .append("\",\"schema_version\":\"").append(contract.schemaVersion())
                .append("\",\"source_sha256\":\"").append(source)
                .append("\",\"runtime_version\":\"").append(escape(runtime)).append("\",");
        json.append("\"").append(contract.container()).append("\":{\"").append(contract.idField())
                .append("\":\"").append(entityId).append("\"}");
        if ("RUN".equals(contract.entityType())) {
            json.append(",\"outcome\":{\"status\":\"PASS\"},\"verification\":{\"status\":\"PASS\"},\"trajectory\":{\"events\":[");
            for (int index = 1; index <= timelineEvents; index++) {
                if (index > 1) json.append(',');
                json.append("{\"event_id\":\"rpf33-event-").append(index)
                        .append("\",\"event_type\":\"timeline_observation\",\"sequence\":").append(index)
                        .append(",\"payload\":{\"status\":\"PASS\"}}");
            }
            json.append("]}}");
        } else {
            json.append(",\"status\":\"PASS\"}");
        }
        return json.toString().getBytes(StandardCharsets.UTF_8);
    }

    private static void writeManifest(Path path, List<Entry> entries) throws IOException {
        Files.createDirectories(path.toAbsolutePath().normalize().getParent());
        try (BufferedWriter writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
            writer.write("entity_type,entity_id,artifact_key,artifact_schema_version,artifact_kind,content_sha256,source_sha256,runtime_version,bytes,timeline_events\n");
            for (Entry entry : entries) {
                writer.write(csv(entry.entityType())); writer.write(',');
                writer.write(csv(entry.entityId())); writer.write(',');
                writer.write(csv(entry.artifactKey())); writer.write(',');
                writer.write(csv(entry.schemaVersion())); writer.write(',');
                writer.write(csv(entry.artifactKind())); writer.write(',');
                writer.write(csv(entry.contentSha256())); writer.write(',');
                writer.write(csv(entry.sourceSha256())); writer.write(',');
                writer.write(csv(entry.runtimeVersion())); writer.write(',');
                writer.write(Long.toString(entry.bytes())); writer.write(',');
                writer.write(Integer.toString(entry.timelineEvents())); writer.write('\n');
            }
        }
    }

    private static String csv(String value) {
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }

    private static byte[] deterministicBytes(int size, int seed) {
        byte[] bytes = new byte[size];
        for (int index = 0; index < size; index++) bytes[index] = (byte) ((index * 31 + seed * 17) & 0xff);
        return bytes;
    }

    private static S3Client client(String endpoint, String access, String secret) {
        return S3Client.builder()
                .endpointOverride(URI.create(endpoint))
                .region(Region.of("us-east-1"))
                .forcePathStyle(true)
                .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create(access, secret)))
                .httpClientBuilder(UrlConnectionHttpClient.builder())
                .requestChecksumCalculation(RequestChecksumCalculation.WHEN_REQUIRED)
                .responseChecksumValidation(ResponseChecksumValidation.WHEN_REQUIRED)
                .overrideConfiguration(ClientOverrideConfiguration.builder()
                        .apiCallTimeout(Duration.ofSeconds(30))
                        .apiCallAttemptTimeout(Duration.ofSeconds(20))
                        .retryPolicy(RetryPolicy.none())
                        .build())
                .build();
    }

    private static Map<String, Contract> contracts() {
        Map<String, Contract> result = new LinkedHashMap<>();
        result.put("RUN", new Contract("RUN", "rpf-run-evidence-v2", "Run Evidence", "run", "run_id"));
        result.put("FAILURE_CASE", new Contract("FAILURE_CASE", "rpf-failure-case-v1", "Failure Case", "failure_case", "failure_case_id"));
        result.put("REGRESSION", new Contract("REGRESSION", "rpf-regression-v1", "Regression", "regression", "regression_id"));
        result.put("REGRESSION_RESULT", new Contract("REGRESSION_RESULT", "rpf-regression-result-v1", "Regression Execution Result", "result", "result_id"));
        result.put("REGRESSION_COLLECTION", new Contract("REGRESSION_COLLECTION", "rpf-regression-collection-v1", "Historical Regression Collection", "collection", "collection_id"));
        result.put("EVALUATION_SUITE", new Contract("EVALUATION_SUITE", "rpf-evaluation-suite-v1", "Evaluation Suite", "suite", "suite_id"));
        result.put("EVALUATION", new Contract("EVALUATION", "rpf-evaluation-result-v1", "Evaluation Result", "evaluation", "evaluation_id"));
        result.put("COMPARISON", new Contract("COMPARISON", "rpf-evaluation-comparison-v1", "Evaluation Comparison", "comparison", "comparison_id"));
        result.put("QUALITY_POLICY", new Contract("QUALITY_POLICY", "rpf-quality-policy-v1", "Quality Policy", "policy", "policy_id"));
        result.put("QUALITY_GATE", new Contract("QUALITY_GATE", "rpf-quality-gate-evaluation-v1", "Quality Gate Evaluation", "gate_evaluation", "gate_evaluation_id"));
        result.put("RELEASE_DECISION", new Contract("RELEASE_DECISION", "rpf-release-decision-v1", "Release Decision", "release_decision", "release_decision_id"));
        result.put("FAILURE_INTELLIGENCE", new Contract("FAILURE_INTELLIGENCE", "rpf-failure-intelligence-v1", "Failure Intelligence", "intelligence", "intelligence_id"));
        result.put("FAILURE_CLUSTER", new Contract("FAILURE_CLUSTER", "rpf-failure-cluster-v1", "Failure Cluster", "cluster", "cluster_id"));
        result.put("VERSION_BISECT", new Contract("VERSION_BISECT", "rpf-version-bisect-v1", "Version Bisect", "bisect", "bisect_id"));
        result.put("STATISTICAL_SAMPLING_PLAN", new Contract("STATISTICAL_SAMPLING_PLAN", "rpf-statistical-sampling-plan-v1", "Statistical Sampling Plan", "sampling_plan", "sampling_plan_id"));
        result.put("STATISTICAL_EVALUATION", new Contract("STATISTICAL_EVALUATION", "rpf-statistical-evaluation-v1", "Statistical Evaluation", "statistical_evaluation", "evaluation_id"));
        result.put("STATISTICAL_COMPARISON", new Contract("STATISTICAL_COMPARISON", "rpf-statistical-comparison-v1", "Statistical Comparison", "statistical_comparison", "comparison_id"));
        result.put("STATISTICAL_POLICY", new Contract("STATISTICAL_POLICY", "rpf-statistical-policy-v1", "Statistical Policy", "statistical_policy", "policy_id"));
        result.put("STATISTICAL_GATE", new Contract("STATISTICAL_GATE", "rpf-statistical-quality-gate-v1", "Statistical Quality Gate", "statistical_gate", "gate_evaluation_id"));
        result.put("STATISTICAL_RELEASE_DECISION", new Contract("STATISTICAL_RELEASE_DECISION", "rpf-statistical-release-decision-v1", "Statistical Release Decision", "statistical_release_decision", "release_decision_id"));
        return result;
    }

    private static Map<String, String> parse(String[] args) {
        Map<String, String> values = new LinkedHashMap<>();
        for (String arg : args) {
            if (!arg.startsWith("--") || !arg.contains("=")) throw new IllegalArgumentException("invalid argument");
            int separator = arg.indexOf('=');
            values.put(arg.substring(2, separator), arg.substring(separator + 1));
        }
        return values;
    }

    private static int boundedInt(String value, int min, int max, String name) {
        int parsed;
        try { parsed = Integer.parseInt(value); } catch (NumberFormatException error) { throw new IllegalArgumentException("invalid " + name); }
        if (parsed < min || parsed > max) throw new IllegalArgumentException("invalid " + name);
        return parsed;
    }

    private static String normalizePrefix(String value) {
        if (value == null || value.isBlank()) return "";
        String normalized = value.replace('\\', '/');
        while (normalized.startsWith("/")) normalized = normalized.substring(1);
        while (normalized.endsWith("/")) normalized = normalized.substring(0, normalized.length() - 1);
        if (normalized.isBlank() || normalized.contains("..")) throw new IllegalArgumentException("unsafe prefix");
        return normalized + "/";
    }

    private static String required(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException("missing " + name);
        return value;
    }

    private static long elapsedMillis(long started) {
        return Math.max(0, (System.nanoTime() - started) / 1_000_000);
    }

    private static String sha256(byte[] content) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content)); }
        catch (Exception error) { throw new IllegalStateException("SHA-256 unavailable", error); }
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static String safeCode(String value) {
        return value.replaceAll("[^A-Za-z0-9_.:-]", "_");
    }

    private static String toJson(Object value) {
        if (value instanceof Map<?, ?> map) {
            StringBuilder result = new StringBuilder("{");
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!first) result.append(',');
                first = false;
                result.append('"').append(escape(String.valueOf(entry.getKey()))).append("\":").append(toJson(entry.getValue()));
            }
            return result.append('}').toString();
        }
        if (value instanceof List<?> list) {
            StringBuilder result = new StringBuilder("[");
            for (int index = 0; index < list.size(); index++) {
                if (index > 0) result.append(',');
                result.append(toJson(list.get(index)));
            }
            return result.append(']').toString();
        }
        if (value instanceof String string) return "\"" + escape(string) + "\"";
        if (value instanceof Boolean || value instanceof Number) return String.valueOf(value);
        return "null";
    }

    private record Contract(String entityType, String schemaVersion, String artifactKind, String container, String idField) {
    }

    private record WorkItem(String entityType, int index, int timelineEvents) {
    }

    private record Entry(
            String entityType,
            String entityId,
            String artifactKey,
            String schemaVersion,
            String artifactKind,
            String contentSha256,
            String sourceSha256,
            String runtimeVersion,
            long bytes,
            int timelineEvents
    ) {
    }
}
