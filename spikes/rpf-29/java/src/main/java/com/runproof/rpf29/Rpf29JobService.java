package com.runproof.rpf29;

import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Executors;

/**
 * Disposable RPF-29 Java candidate.
 *
 * This is deliberately not the formal Control Plane. It exercises the
 * durable-job boundary with PostgreSQL and emits the smallest OTLP/HTTP JSON
 * payload needed to test context propagation. The production decision remains
 * open between supported SDK/manual instrumentation and selective auto-agent
 * instrumentation.
 */
public final class Rpf29JobService {
    private final String jdbcUrl;
    private final String jdbcUser;
    private final String jdbcPassword;
    private final String otlpEndpoint;
    private final Path auditPath;
    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(250))
            .build();
    private HttpServer server;

    private Rpf29JobService(String jdbcUrl, String jdbcUser, String jdbcPassword, String otlpEndpoint, Path auditPath) {
        this.jdbcUrl = jdbcUrl;
        this.jdbcUser = jdbcUser;
        this.jdbcPassword = jdbcPassword;
        this.otlpEndpoint = otlpEndpoint;
        this.auditPath = auditPath;
    }

    public static void main(String[] args) throws Exception {
        Map<String, String> options = parseArgs(args);
        int requestedPort = Integer.parseInt(options.getOrDefault("port", "0"));
        String jdbcUrl = required(options, "db-url");
        String user = required(options, "db-user");
        String password = System.getenv("RPF29_DB_PASSWORD");
        if (password == null) password = "";
        String otlp = required(options, "otlp");
        Path audit = Path.of(required(options, "audit")).toAbsolutePath().normalize();
        String readyFile = options.get("ready-file");

        Class.forName("org.postgresql.Driver");
        Rpf29JobService service = new Rpf29JobService(jdbcUrl, user, password, otlp, audit);
        service.initializeSchema();
        service.start(requestedPort);
        int port = service.server.getAddress().getPort();
        if (readyFile != null) {
            Path path = Path.of(readyFile).toAbsolutePath().normalize();
            Files.createDirectories(path.getParent());
            Files.writeString(path, Json.object(Map.of("ready", true, "port", port)), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        }
        System.out.println("RPF29_READY " + Json.object(Map.of("port", port)));
        System.out.flush();
        Runtime.getRuntime().addShutdownHook(new Thread(service::stop));
    }

    private static Map<String, String> parseArgs(String[] args) {
        Map<String, String> values = new LinkedHashMap<>();
        for (int index = 0; index < args.length; index++) {
            String item = args[index];
            if (!item.startsWith("--") || index + 1 >= args.length) continue;
            values.put(item.substring(2), args[++index]);
        }
        return values;
    }

    private static String required(Map<String, String> options, String key) {
        String value = options.get(key);
        if (value == null || value.isBlank()) throw new IllegalArgumentException("missing option: " + key);
        return value;
    }

    private void initializeSchema() throws SQLException {
        try (Connection connection = connection()) {
            connection.setAutoCommit(false);
            try (var statement = connection.createStatement()) {
                statement.executeUpdate("""
                        CREATE TABLE IF NOT EXISTS rpf29_job (
                            job_id VARCHAR(160) PRIMARY KEY,
                            run_id VARCHAR(160) NOT NULL,
                            operation_id VARCHAR(160) NOT NULL,
                            environment_id VARCHAR(160) NOT NULL,
                            fault_profile VARCHAR(80) NOT NULL,
                            trace_id VARCHAR(64) NOT NULL,
                            span_id VARCHAR(32) NOT NULL,
                            traceparent VARCHAR(160) NOT NULL,
                            active_attempt_id VARCHAR(160) NOT NULL,
                            attempt_count INTEGER NOT NULL,
                            state VARCHAR(32) NOT NULL
                        )
                        """);
                statement.executeUpdate("""
                        CREATE TABLE IF NOT EXISTS rpf29_attempt (
                            attempt_id VARCHAR(160) PRIMARY KEY,
                            job_id VARCHAR(160) NOT NULL REFERENCES rpf29_job(job_id),
                            status VARCHAR(32) NOT NULL,
                            trace_id VARCHAR(64) NOT NULL,
                            parent_span_id VARCHAR(32) NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """);
            }
            connection.commit();
        }
    }

    private Connection connection() throws SQLException {
        return DriverManager.getConnection(jdbcUrl, jdbcUser, jdbcPassword);
    }

    private void start(int port) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/health", exchange -> respond(exchange, 200, Map.of("status", "HEALTHY", "service", "rpf29-java-job-candidate")));
        server.createContext("/jobs", new JobsHandler());
        server.setExecutor(Executors.newFixedThreadPool(8));
        server.start();
    }

    private void stop() {
        if (server != null) server.stop(0);
    }

    private final class JobsHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            try {
                String path = exchange.getRequestURI().getPath();
                String[] parts = path.split("/");
                if ("POST".equalsIgnoreCase(exchange.getRequestMethod()) && "/jobs".equals(path)) {
                    createJob(exchange);
                    return;
                }
                if (parts.length == 4 && "POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                    String jobId = parts[2];
                    switch (parts[3]) {
                        case "claim" -> claimJob(exchange, jobId);
                        case "reclaim" -> reclaimJob(exchange, jobId);
                        case "complete" -> completeJob(exchange, jobId);
                        default -> respond(exchange, 404, Map.of("error", "NOT_FOUND"));
                    }
                    return;
                }
                respond(exchange, 404, Map.of("error", "NOT_FOUND"));
            } catch (Exception error) {
                respond(exchange, 500, Map.of("error", "JAVA_CANDIDATE_FAILURE"));
            }
        }
    }

    private void createJob(HttpExchange exchange) throws Exception {
        Map<String, String> input = flatJson(readBody(exchange));
        String jobId = requiredInput(input, "job_id");
        String runId = requiredInput(input, "run_id");
        String attemptId = requiredInput(input, "attempt_id");
        String operationId = requiredInput(input, "operation_id");
        String environmentId = requiredInput(input, "environment_id");
        String faultProfile = requiredInput(input, "fault_profile");
        Span span = span("runproof.job.create", null, canonicalAttributes(input, "QUEUED", "rpf29-java-job-candidate"));
        span.event("job.created", Map.of("rpf.durable_boundary", "postgresql"));
        try (Connection connection = connection()) {
            connection.setAutoCommit(false);
            try (PreparedStatement job = connection.prepareStatement("""
                    INSERT INTO rpf29_job(job_id, run_id, operation_id, environment_id, fault_profile, trace_id, span_id, traceparent, active_attempt_id, attempt_count, state)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'QUEUED')
                    """);
                 PreparedStatement attempt = connection.prepareStatement("""
                    INSERT INTO rpf29_attempt(attempt_id, job_id, status, trace_id, parent_span_id) VALUES (?, ?, 'QUEUED', ?, ?)
                    """)) {
                job.setString(1, jobId);
                job.setString(2, runId);
                job.setString(3, operationId);
                job.setString(4, environmentId);
                job.setString(5, faultProfile);
                job.setString(6, span.trace.traceId);
                job.setString(7, span.trace.spanId);
                job.setString(8, span.trace.traceparent());
                job.setString(9, attemptId);
                job.executeUpdate();
                attempt.setString(1, attemptId);
                attempt.setString(2, jobId);
                attempt.setString(3, span.trace.traceId);
                attempt.setString(4, span.trace.spanId);
                attempt.executeUpdate();
            }
            connection.commit();
        } catch (Exception error) {
            span.end("ERROR", "job_create_failed");
            throw error;
        }
        span.end("OK", null);
        respond(exchange, 201, Map.of("job_id", jobId, "traceparent", span.trace.traceparent(), "trace_id", span.trace.traceId, "attempt_id", attemptId, "state", "QUEUED"));
    }

    private void reclaimJob(HttpExchange exchange, String jobId) throws Exception {
        Job row = loadJob(jobId);
        if (row == null) {
            respond(exchange, 404, Map.of("error", "JOB_NOT_FOUND"));
            return;
        }
        Span span = span("runproof.job.reclaim", row.context(), row.attributes("RECLAIMING"));
        String oldAttempt = row.activeAttemptId;
        String newAttempt = row.jobId + "-attempt-" + (row.attemptCount + 1);
        try (Connection connection = connection()) {
            connection.setAutoCommit(false);
            try (PreparedStatement expire = connection.prepareStatement("UPDATE rpf29_attempt SET status='EXPIRED' WHERE attempt_id=?");
                 PreparedStatement insert = connection.prepareStatement("INSERT INTO rpf29_attempt(attempt_id, job_id, status, trace_id, parent_span_id) VALUES (?, ?, 'QUEUED', ?, ?)");
                 PreparedStatement update = connection.prepareStatement("UPDATE rpf29_job SET active_attempt_id=?, attempt_count=?, state='QUEUED' WHERE job_id=?")) {
                expire.setString(1, oldAttempt);
                expire.executeUpdate();
                insert.setString(1, newAttempt);
                insert.setString(2, jobId);
                insert.setString(3, row.trace.traceId);
                insert.setString(4, span.trace.spanId);
                insert.executeUpdate();
                update.setString(1, newAttempt);
                update.setInt(2, row.attemptCount + 1);
                update.setString(3, jobId);
                update.executeUpdate();
            }
            connection.commit();
        }
        span.link(row.trace, Map.of("rpf.link.type", "expired-attempt"));
        span.event("attempt.reclaimed", Map.of("rpf.previous_attempt", oldAttempt, "rpf.new_attempt", newAttempt));
        span.end("OK", null);
        respond(exchange, 200, Map.of("job_id", jobId, "trace_id", row.trace.traceId, "previous_attempt_id", oldAttempt, "attempt_id", newAttempt, "attempt_model", "same-trace-new-attempt-subtree-with-link"));
    }

    private void claimJob(HttpExchange exchange, String jobId) throws Exception {
        Job row = loadJob(jobId);
        if (row == null) {
            respond(exchange, 404, Map.of("error", "JOB_NOT_FOUND"));
            return;
        }
        Context requestParent = Context.parse(exchange.getRequestHeaders().getFirst("traceparent"));
        Span span = span("runproof.job.claim", row.context(), row.attributes("CLAIMED"));
        span.link(requestParent, Map.of("rpf.link.type", "claim-request"));
        try (Connection connection = connection();
             PreparedStatement updateAttempt = connection.prepareStatement("UPDATE rpf29_attempt SET status='CLAIMED' WHERE attempt_id=?");
             PreparedStatement updateJob = connection.prepareStatement("UPDATE rpf29_job SET state='CLAIMED' WHERE job_id=?")) {
            updateAttempt.setString(1, row.activeAttemptId);
            updateAttempt.executeUpdate();
            updateJob.setString(1, jobId);
            updateJob.executeUpdate();
        }
        span.event("job.context.resumed", Map.of("rpf.context_source", "durable-postgresql-metadata"));
        span.end("OK", null);
        respond(exchange, 200, Map.of(
                "job_id", jobId,
                "run_id", row.runId,
                "operation_id", row.operationId,
                "environment_id", row.environmentId,
                "fault_profile", row.faultProfile,
                "attempt_id", row.activeAttemptId,
                "attempt_count", row.attemptCount,
                "traceparent", row.trace.traceparent(),
                "trace_id", row.trace.traceId,
                "state", "CLAIMED"));
    }

    private void completeJob(HttpExchange exchange, String jobId) throws Exception {
        Job row = loadJob(jobId);
        if (row == null) {
            respond(exchange, 404, Map.of("error", "JOB_NOT_FOUND"));
            return;
        }
        Context parent = Context.parse(exchange.getRequestHeaders().getFirst("traceparent"));
        Span span = span("runproof.job.complete", parent, row.attributes("COMPLETED"));
        try (Connection connection = connection();
             PreparedStatement updateAttempt = connection.prepareStatement("UPDATE rpf29_attempt SET status='COMPLETED' WHERE attempt_id=?");
             PreparedStatement updateJob = connection.prepareStatement("UPDATE rpf29_job SET state='COMPLETED' WHERE job_id=?")) {
            updateAttempt.setString(1, row.activeAttemptId);
            updateAttempt.executeUpdate();
            updateJob.setString(1, jobId);
            updateJob.executeUpdate();
        }
        span.end("OK", null);
        respond(exchange, 200, Map.of("job_id", jobId, "state", "COMPLETED", "attempt_id", row.activeAttemptId));
    }

    private Job loadJob(String jobId) throws SQLException {
        try (Connection connection = connection();
             PreparedStatement statement = connection.prepareStatement("SELECT job_id, run_id, operation_id, environment_id, fault_profile, trace_id, span_id, active_attempt_id, attempt_count, state FROM rpf29_job WHERE job_id=?")) {
            statement.setString(1, jobId);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) return null;
                return new Job(
                        result.getString("job_id"), result.getString("run_id"), result.getString("operation_id"),
                        result.getString("environment_id"), result.getString("fault_profile"),
                        new Context(result.getString("trace_id"), result.getString("span_id")),
                        result.getString("active_attempt_id"), result.getInt("attempt_count"), result.getString("state"));
            }
        }
    }

    private Span span(String name, Context parent, Map<String, Object> attributes) {
        return new Span(name, parent, attributes);
    }

    private Map<String, Object> canonicalAttributes(Map<String, String> input, String outcome, String service) {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("service.name", service);
        values.put("rpf.job_id", input.get("job_id"));
        values.put("rpf.attempt_id", input.get("attempt_id"));
        values.put("rpf.run_id", input.get("run_id"));
        values.put("rpf.environment_id", input.get("environment_id"));
        values.put("rpf.operation_id", input.get("operation_id"));
        values.put("rpf.fault_profile", input.get("fault_profile"));
        if (input.get("scenario_id") != null) values.put("rpf.scenario_id", input.get("scenario_id"));
        values.put("rpf.outcome", outcome);
        return values;
    }

    private static String requiredInput(Map<String, String> input, String key) {
        String value = input.get(key);
        if (value == null || value.isBlank()) throw new IllegalArgumentException("missing field");
        return value;
    }

    private static String readBody(HttpExchange exchange) throws IOException {
        return new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
    }

    private static void respond(HttpExchange exchange, int status, Map<String, ?> value) throws IOException {
        byte[] body = Json.object(value).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, body.length);
        try (var output = exchange.getResponseBody()) {
            output.write(body);
        }
    }

    private final class Span {
        private final String name;
        private final Context parent;
        private final Context trace;
        private final long startedAt = System.currentTimeMillis();
        private final Map<String, Object> attributes = new LinkedHashMap<>();
        private final List<Map<String, Object>> events = new ArrayList<>();
        private final List<Map<String, Object>> links = new ArrayList<>();

        private Span(String name, Context parent, Map<String, Object> attributes) {
            this.name = name;
            this.parent = parent;
            this.trace = Context.child(parent);
            if (attributes != null) this.attributes.putAll(attributes);
        }

        private void event(String eventName, Map<String, ?> values) {
            events.add(Map.of("name", eventName, "time_unix_nano", Long.toString((startedAt + 1) * 1_000_000L), "attributes", values));
        }

        private void link(Context context, Map<String, ?> values) {
            if (context != null) links.add(Map.of("trace_id", context.traceId, "span_id", context.spanId, "attributes", values));
        }

        private void end(String status, String errorType) {
            if (errorType != null) attributes.put("rpf.error_type", errorType);
            attributes.putIfAbsent("rpf.telemetry_completeness", "full-candidate");
            Map<String, Object> span = new LinkedHashMap<>();
            span.put("trace_id", trace.traceId);
            span.put("span_id", trace.spanId);
            if (parent != null) span.put("parent_span_id", parent.spanId);
            span.put("name", name);
            span.put("kind", 1);
            span.put("start_time_unix_nano", Long.toString(startedAt * 1_000_000L));
            span.put("end_time_unix_nano", Long.toString(System.currentTimeMillis() * 1_000_000L));
            span.put("attributes", attributes);
            span.put("events", events);
            span.put("links", links);
            span.put("status", Map.of("code", "OK".equals(status) ? 1 : "ERROR".equals(status) ? 2 : 0, "message", errorType == null ? "" : errorType));
            span.put("service_name", "rpf29-java-job-candidate");
            boolean exported = export(span);
            span.put("collector_exported", exported);
            appendAudit(span, exported);
        }
    }

    private boolean export(Map<String, Object> span) {
        try {
            String body = Json.object(Map.of("resourceSpans", List.of(Map.of(
                    "resource", Map.of("attributes", List.of(Map.of("key", "service.name", "value", Map.of("stringValue", "rpf29-java-job-candidate")))),
                    "scopeSpans", List.of(Map.of("scope", Map.of("name", "runproof.rpf29.manual", "version", "0.1"), "spans", List.of(otlpSpan(span))))))));
            HttpRequest request = HttpRequest.newBuilder(URI.create(otlpEndpoint + (otlpEndpoint.endsWith("/v1/traces") ? "" : "/v1/traces")))
                    .timeout(Duration.ofMillis(350))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();
            HttpResponse<Void> response = httpClient.send(request, HttpResponse.BodyHandlers.discarding());
            return response.statusCode() >= 200 && response.statusCode() < 300;
        } catch (Exception ignored) {
            return false;
        }
    }

    private static Map<String, Object> otlpSpan(Map<String, Object> span) {
        Map<String, Object> copy = new LinkedHashMap<>(span);
        copy.remove("service_name");
        copy.remove("collector_exported");
        return copy;
    }

    private void appendAudit(Map<String, Object> span, boolean exported) {
        try {
            Map<String, Object> copy = new LinkedHashMap<>(span);
            copy.put("collector_exported", exported);
            Files.createDirectories(auditPath.getParent());
            Files.writeString(auditPath, Json.object(copy) + System.lineSeparator(), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException ignored) {
            // Audit output must not change the candidate's product result.
        }
    }

    private record Job(String jobId, String runId, String operationId, String environmentId, String faultProfile,
                       Context trace, String activeAttemptId, int attemptCount, String state) {
        private Map<String, Object> attributes(String outcome) {
            return Map.of(
                    "service.name", "rpf29-java-job-candidate",
                    "rpf.job_id", jobId,
                    "rpf.attempt_id", activeAttemptId,
                    "rpf.run_id", runId,
                    "rpf.environment_id", environmentId,
                    "rpf.operation_id", operationId,
                    "rpf.fault_profile", faultProfile,
                    "rpf.outcome", outcome);
        }

        private Context context() {
            return trace;
        }
    }

    private static final class Context {
        private final String traceId;
        private final String spanId;

        private Context(String traceId, String spanId) {
            this.traceId = traceId;
            this.spanId = spanId;
        }

        private static Context child(Context parent) {
            return new Context(parent == null ? randomHex(32) : parent.traceId, randomHex(16));
        }

        private static Context parse(String value) {
            if (value == null) return null;
            String[] parts = value.split("-");
            if (parts.length != 4 || parts[1].length() != 32 || parts[2].length() != 16) return null;
            return new Context(parts[1], parts[2]);
        }

        private String traceparent() {
            return "00-" + traceId + "-" + spanId + "-01";
        }
    }

    private static String randomHex(int length) {
        String value = UUID.randomUUID().toString().replace("-", "") + UUID.randomUUID().toString().replace("-", "");
        return value.substring(0, length);
    }

    private static Map<String, String> flatJson(String body) {
        Map<String, String> values = new LinkedHashMap<>();
        java.util.regex.Matcher matcher = java.util.regex.Pattern.compile("\\\"([A-Za-z0-9_.-]+)\\\"\\s*:\\s*\\\"((?:\\\\.|[^\\\"\\\\])*)\\\"").matcher(body);
        while (matcher.find()) values.put(matcher.group(1), matcher.group(2).replace("\\\"", "\""));
        return values;
    }

    private static final class Json {
        private static String object(Map<String, ?> values) {
            return value(values);
        }

        private static String value(Object item) {
            if (item == null) return "null";
            if (item instanceof String string) return quote(string);
            if (item instanceof Number || item instanceof Boolean) return item.toString();
            if (item instanceof Map<?, ?> map) {
                StringBuilder output = new StringBuilder("{");
                boolean first = true;
                for (Map.Entry<?, ?> entry : map.entrySet()) {
                    if (!first) output.append(',');
                    first = false;
                    output.append(quote(String.valueOf(entry.getKey()))).append(':').append(value(entry.getValue()));
                }
                return output.append('}').toString();
            }
            if (item instanceof Iterable<?> iterable) {
                StringBuilder output = new StringBuilder("[");
                boolean first = true;
                for (Object element : iterable) {
                    if (!first) output.append(',');
                    first = false;
                    output.append(value(element));
                }
                return output.append(']').toString();
            }
            return quote(String.valueOf(item));
        }

        private static String quote(String text) {
            StringBuilder output = new StringBuilder("\"");
            for (char character : text.toCharArray()) {
                switch (character) {
                    case '\\' -> output.append("\\\\");
                    case '"' -> output.append("\\\"");
                    case '\n' -> output.append("\\n");
                    case '\r' -> output.append("\\r");
                    case '\t' -> output.append("\\t");
                    default -> output.append(character);
                }
            }
            return output.append('"').toString();
        }
    }
}
