package com.runproof.controlplane;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

import static com.runproof.controlplane.ProbeExceptions.EntityNotFoundException;
import static com.runproof.controlplane.ProbeExceptions.IdentityConflictException;
import static com.runproof.controlplane.ProbeExceptions.InvalidEvidenceException;
import static com.runproof.controlplane.ProbeExceptions.RequestValidationException;

/**
 * Formal PostgreSQL-backed durable execution boundary.
 *
 * <p>The job row is a mutable coordination projection. Attempts and events
 * retain the execution history, operations retain stable side-effect identity,
 * and evidence rows retain immutable artifact references. The controller does
 * not execute an Agent and never grants release or decision authority.</p>
 */
@RestController
@RequestMapping("/api/v1")
public class DurableExecutionController {

    private static final Set<String> TERMINAL_STATES = Set.of("COMPLETED", "FAILED_PLATFORM", "CANCELLED");
    private static final Set<String> OWNER_STATES = Set.of("CLAIMED", "RUNNING", "CANCEL_REQUESTED");
    private static final Set<String> UNSAFE_OPERATION_STATES = Set.of("PREPARED", "IN_FLIGHT", "UNKNOWN_OUTCOME");
    private static final Set<String> EVIDENCE_OUTCOMES = Set.of("PASS", "FAIL", "ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED");
    private static final Set<String> EVIDENCE_TYPES = Set.of(
            "RUN", "FAILURE_CASE", "REGRESSION", "REGRESSION_RESULT", "REGRESSION_COLLECTION",
            "EVALUATION_SUITE", "EVALUATION", "COMPARISON", "QUALITY_POLICY", "QUALITY_GATE", "RELEASE_DECISION",
            "FAILURE_INTELLIGENCE", "FAILURE_CLUSTER", "VERSION_BISECT",
            "STATISTICAL_SAMPLING_PLAN", "STATISTICAL_EVALUATION", "STATISTICAL_COMPARISON", "STATISTICAL_POLICY", "STATISTICAL_GATE", "STATISTICAL_RELEASE_DECISION"
    );
    private static final Set<String> FORBIDDEN_KEYS = Set.of(
            "authorization", "token", "secret", "password", "credential", "api_key", "apikey",
            "prompt", "message", "messages", "reasoning", "chain_of_thought", "private_thought", "private_reasoning"
    );

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final TransactionTemplate transactions;
    private final CanonicalMetadataService canonicalMetadataService;
    private final AuthService authService;
    private final ObservabilityService observability;
    private final boolean probeEnabled;

    public DurableExecutionController(
            JdbcTemplate jdbc,
            ObjectMapper mapper,
            PlatformTransactionManager transactionManager,
            CanonicalMetadataService canonicalMetadataService,
            AuthService authService,
            ObservabilityService observability,
            @Value("${rpf.probe.enabled:false}") boolean probeEnabled
    ) {
        this.jdbc = jdbc;
        this.mapper = mapper;
        this.transactions = new TransactionTemplate(transactionManager);
        this.canonicalMetadataService = canonicalMetadataService;
        this.authService = authService;
        this.observability = observability;
        this.probeEnabled = probeEnabled;
    }

    @GetMapping("/jobs")
    public Map<String, Object> listJobs(
            HttpServletRequest request,
            @RequestParam(name = "state", required = false) String state,
            @RequestParam(name = "target_type", required = false) String targetType,
            @RequestParam(name = "eligible", defaultValue = "false") boolean eligible,
            @RequestParam(name = "limit", defaultValue = "50") int limit
    ) {
        authService.require(request, "metadata:read");
        try (ObservabilityService.SpanScope ignored = observability.span("runproof.job.read", Map.of("runproof.target.type", targetType == null ? "ANY" : targetType.toUpperCase(Locale.ROOT)))) {
        int boundedLimit = Math.max(1, Math.min(limit, 100));
        List<String> conditions = new ArrayList<>();
        List<Object> args = new ArrayList<>();
        if (eligible && state != null && !state.isBlank()) {
            throw new RequestValidationException("INCOMPATIBLE_JOB_DISCOVERY_FILTER", "Eligible discovery cannot be combined with an explicit state filter.");
        }
        if (eligible) {
            conditions.add("(state IN ('QUEUED', 'RECONCILE_REQUIRED') OR (state IN ('CLAIMED', 'RUNNING', 'CANCEL_REQUESTED') AND lease_expires_at IS NOT NULL AND lease_expires_at <= CURRENT_TIMESTAMP))");
        }
        if (state != null && !state.isBlank()) {
            conditions.add("state = ?");
            args.add(requiredState(state));
        }
        if (targetType != null && !targetType.isBlank()) {
            conditions.add("target_type = ?");
            args.add(requiredIdValue(targetType.trim().toUpperCase(Locale.ROOT), "target_type"));
        }
        String where = conditions.isEmpty() ? "" : " WHERE " + String.join(" AND ", conditions);
        String sql = "SELECT job_id FROM rpf_execution_job" + where + " ORDER BY created_at, job_id LIMIT " + boundedLimit;
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : jdbc.queryForList(sql, args.toArray())) {
            items.add(snapshot(findJob(text(row, "job_id"), false, true)));
        }
        return Map.of("items", items, "limit", boundedLimit, "discovery", eligible ? "ELIGIBLE" : "HISTORY");
        }
    }

    @GetMapping("/execution-metrics")
    public Map<String, Object> metrics(HttpServletRequest request) {
        authService.require(request, "metadata:read");
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("queued_jobs", count("SELECT COUNT(*) FROM rpf_execution_job WHERE state='QUEUED'"));
        result.put("claimed_or_running_jobs", count("SELECT COUNT(*) FROM rpf_execution_job WHERE state IN ('CLAIMED','RUNNING','CANCEL_REQUESTED')"));
        result.put("reconcile_required_jobs", count("SELECT COUNT(*) FROM rpf_execution_job WHERE state='RECONCILE_REQUIRED'"));
        result.put("completed_jobs", count("SELECT COUNT(*) FROM rpf_execution_job WHERE state='COMPLETED'"));
        result.put("platform_failed_jobs", count("SELECT COUNT(*) FROM rpf_execution_job WHERE state='FAILED_PLATFORM'"));
        result.put("cancelled_jobs", count("SELECT COUNT(*) FROM rpf_execution_job WHERE state='CANCELLED'"));
        result.put("lease_expiry_count", count("SELECT COUNT(*) FROM rpf_execution_attempt WHERE status='EXPIRED'"));
        result.put("reclaim_count", count("SELECT COUNT(*) FROM rpf_execution_event WHERE event_type='LEASE_EXPIRED_REQUEUED'"));
        result.put("stale_attempt_rejection_count", count("SELECT COUNT(*) FROM control_plane_audit WHERE reason_code='STALE_ATTEMPT'"));
        result.put("attempts_total", count("SELECT COUNT(*) FROM rpf_execution_attempt"));
        result.put("eligible_jobs", count("SELECT COUNT(*) FROM rpf_execution_job WHERE state IN ('QUEUED', 'RECONCILE_REQUIRED') OR (state IN ('CLAIMED', 'RUNNING', 'CANCEL_REQUESTED') AND lease_expires_at IS NOT NULL AND lease_expires_at <= CURRENT_TIMESTAMP)"));
        result.put("observability_boundary", "READ_API_COUNTERS_NO_PROMETHEUS_BACKEND");
        return result;
    }

    @GetMapping("/jobs/{jobId}")
    public Map<String, Object> getJob(HttpServletRequest request, @PathVariable String jobId) {
        authService.require(request, "metadata:read");
        mark(request, "EXECUTION_JOB", jobId);
        try (ObservabilityService.SpanScope ignored = observability.span("runproof.job.read", Map.of("runproof.job.id", requiredIdValue(jobId, "job_id")))) {
            return snapshot(findJob(requiredIdValue(jobId, "job_id"), false, true));
        }
    }

    @PostMapping("/jobs")
    public ResponseEntity<Map<String, Object>> submit(HttpServletRequest request, @RequestBody Map<String, Object> rawBody) {
        authService.require(request, "execution:submit");
        Map<String, Object> body = requiredBody(rawBody);
        String jobId = optionalId(body, "job_id", "job-" + UUID.randomUUID());
        String idempotencyKey = requiredId(body, "idempotency_key");
        String fingerprint = requiredId(body, "request_fingerprint");
        String jobType = requiredId(body, "job_type").toUpperCase(Locale.ROOT);
        String targetType = requiredId(body, "target_type").toUpperCase(Locale.ROOT);
        String targetId = requiredId(body, "target_id");
        String correlationId = optionalId(body, "correlation_id", "rpf14-" + UUID.randomUUID());
        Map<String, Object> payloadRef = payloadRef(body.get("payload_ref"));
        mark(request, "EXECUTION_JOB", jobId);
        try (ObservabilityService.SpanScope submitSpan = observability.span("runproof.job.submit", Map.of(
                "runproof.job.id", jobId,
                "runproof.job.type", jobType,
                "runproof.target.type", targetType
        ))) {
        String observabilityContext = json(submitSpan.contextDocument());
        Map<String, Object> result = transactions.execute(status -> {
            Map<String, Object> existing = findJobByIdempotency(idempotencyKey, true);
            if (existing != null) {
                ensureSameSubmission(existing, fingerprint, jobType, targetType, targetId);
                return response("IDEMPOTENT_REPLAY", true, existing.get("job_id"), snapshot(existing));
            }
            Map<String, Object> byId = findJob(jobId, true, false);
            if (byId != null) {
                ensureSameSubmission(byId, fingerprint, jobType, targetType, targetId);
                return response("IDEMPOTENT_REPLAY", true, byId.get("job_id"), snapshot(byId));
            }
            Instant now = Instant.now();
            int inserted = jdbc.update("""
                    INSERT INTO rpf_execution_job(
                        job_id, idempotency_key, request_fingerprint, job_type, target_type, target_id,
                        payload_ref_json, correlation_id, state, version, attempt_number,
                        cancel_requested, timeout_requested, otel_context_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', 0, 0, FALSE, FALSE, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    jobId, idempotencyKey, fingerprint, jobType, targetType, targetId,
                    json(payloadRef), correlationId, observabilityContext, Timestamp.from(now), Timestamp.from(now)
            );
            if (inserted == 0) {
                Map<String, Object> winner = findJobByIdempotency(idempotencyKey, true);
                if (winner == null) winner = findJob(jobId, true, false);
                if (winner == null) throw new IdentityConflictException("SUBMIT_RACE_UNRESOLVED", "Concurrent durable submission did not produce a readable winner.");
                ensureSameSubmission(winner, fingerprint, jobType, targetType, targetId);
                return response("IDEMPOTENT_REPLAY", true, winner.get("job_id"), snapshot(winner));
            }
            insertEvent(jobId, null, "QUEUED", "JOB_SUBMITTED", null, null, 0L, "DURABLE_SUBMIT", now);
            return response("SUBMITTED", false, jobId, snapshot(findJob(jobId, false, true)));
        });
        return ResponseEntity.status(Boolean.TRUE.equals(result.get("already_exists")) ? HttpStatus.OK : HttpStatus.CREATED).body(result);
        }
    }

    @PostMapping("/jobs/{jobId}/claim")
    public ResponseEntity<Map<String, Object>> claim(
            HttpServletRequest request,
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String workerId = requiredId(body, "worker_id");
        int leaseSeconds = integer(body, "lease_seconds", 1, 60, 15);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        mark(request, "EXECUTION_JOB", normalizedJobId);
        try (ObservabilityService.SpanScope ignored = observability.span("runproof.job.claim", Map.of("runproof.job.id", normalizedJobId))) {
            return ResponseEntity.ok(transactions.execute(status -> claimLocked(normalizedJobId, workerId, leaseSeconds)));
        }
    }

    @PostMapping("/jobs/{jobId}/start")
    public Map<String, Object> start(
            HttpServletRequest request,
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        mark(request, "EXECUTION_JOB", normalizedJobId);
        String attemptObservabilityContext = safeDiagnosticContext(body.get("observability_context"));
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            if ("RUNNING".equals(job.get("state"))) {
                requireOwner(job, body);
                return response("ALREADY_RUNNING", true, normalizedJobId, snapshot(job));
            }
            requireOwner(job, body);
            if (!"CLAIMED".equals(job.get("state"))) {
                throw new RequestValidationException("JOB_NOT_STARTABLE", "Only a claimed attempt can enter RUNNING.");
            }
            Instant now = Instant.now();
            long nextVersion = version(job) + 1;
            jdbc.update("UPDATE rpf_execution_job SET state='RUNNING', version=?, updated_at=? WHERE job_id=?", nextVersion, Timestamp.from(now), normalizedJobId);
            jdbc.update("UPDATE rpf_execution_attempt SET status='RUNNING', lease_version=?, otel_context_json=COALESCE(?, otel_context_json), started_at=COALESCE(started_at, ?) WHERE attempt_id=?", nextVersion, attemptObservabilityContext, Timestamp.from(now), job.get("active_attempt_id"));
            insertEvent(normalizedJobId, "CLAIMED", "RUNNING", "ATTEMPT_STARTED", text(job, "active_attempt_id"), null, nextVersion, "WORKER_STARTED", now);
            return response("RUNNING", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
        });
    }

    @PostMapping("/jobs/{jobId}/heartbeat")
    public Map<String, Object> heartbeat(
            HttpServletRequest request,
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        int leaseSeconds = integer(body, "lease_seconds", 1, 60, 15);
        mark(request, "EXECUTION_JOB", normalizedJobId);
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Instant now = Instant.now();
            Instant expires = now.plusSeconds(leaseSeconds);
            long nextVersion = version(job) + 1;
            jdbc.update("UPDATE rpf_execution_job SET version=?, lease_expires_at=?, heartbeat_at=?, updated_at=? WHERE job_id=?",
                    nextVersion, Timestamp.from(expires), Timestamp.from(now), Timestamp.from(now), normalizedJobId);
            jdbc.update("UPDATE rpf_execution_attempt SET lease_version=?, lease_expires_at=?, heartbeat_at=? WHERE attempt_id=?",
                    nextVersion, Timestamp.from(expires), Timestamp.from(now), job.get("active_attempt_id"));
            insertEvent(normalizedJobId, text(job, "state"), text(job, "state"), "LEASE_HEARTBEAT", text(job, "active_attempt_id"), null, nextVersion, "LEASE_EXTENDED", now);
            Map<String, Object> updated = findJob(normalizedJobId, false, true);
            Map<String, Object> result = response("HEARTBEAT_ACCEPTED", false, normalizedJobId, snapshot(updated));
            result.put("lease", leaseDetails(updated, body.get("lease_token"), nextVersion, expires));
            return result;
        });
    }

    @PostMapping("/jobs/{jobId}/operations")
    public Map<String, Object> prepareOperation(
            HttpServletRequest request,
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String operationId = requiredId(body, "operation_id");
        String environmentId = requiredId(body, "environment_id");
        String operationFingerprint = requiredId(body, "operation_fingerprint");
        ensureSafe(Map.of(
                "operation_id", operationId,
                "environment_id", environmentId,
                "operation_fingerprint", operationFingerprint
        ));
        mark(request, "EXECUTION_OPERATION", operationId);
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> existing = findOperation(operationId, true);
            if (existing != null) {
                if (!Objects.equals(existing.get("job_id"), normalizedJobId)
                        || !Objects.equals(existing.get("operation_fingerprint"), operationFingerprint)) {
                throw new IdentityConflictException("OPERATION_IDENTITY_CONFLICT", "operation_id is already bound to a different operation.");
                }
                return operationResponse("IDEMPOTENT_REPLAY", true, existing);
            }
            Instant now = Instant.now();
            int inserted = jdbc.update("""
                    INSERT INTO rpf_execution_operation(
                        operation_id, job_id, attempt_id, environment_id, operation_fingerprint,
                        status, effect_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'PREPARED', 0, ?, ?)
                    ON CONFLICT DO NOTHING
                    """, operationId, normalizedJobId, job.get("active_attempt_id"), environmentId,
                    operationFingerprint, Timestamp.from(now), Timestamp.from(now));
            if (inserted == 0) {
                Map<String, Object> winner = findOperation(operationId, true);
                if (winner == null) throw new IdentityConflictException("OPERATION_RACE_UNRESOLVED", "Concurrent operation preparation did not produce a readable winner.");
                if (!Objects.equals(winner.get("job_id"), normalizedJobId)
                        || !Objects.equals(winner.get("operation_fingerprint"), operationFingerprint)) {
                    throw new IdentityConflictException("OPERATION_IDENTITY_CONFLICT", "operation_id is already bound to a different operation.");
                }
                return operationResponse("IDEMPOTENT_REPLAY", true, winner);
            }
            return operationResponse("PREPARED", false, findOperation(operationId, false));
        });
    }

    /** Mark the dispatch boundary without simulating a product side effect. */
    @PostMapping("/jobs/{jobId}/operations/{operationId}/dispatch")
    public Map<String, Object> dispatchOperation(
            HttpServletRequest request,
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("CONFIRMED".equals(current)) return operationResponse("IDEMPOTENT_REPLAY", true, operation);
            if ("IN_FLIGHT".equals(current)) return operationResponse("DISPATCHED", true, operation);
            if (!Set.of("PREPARED", "NOT_SUBMITTED").contains(current)) {
                throw new RequestValidationException("OPERATION_NOT_DISPATCHABLE", "The operation is not at a safe dispatch boundary.");
            }
            jdbc.update("UPDATE rpf_execution_operation SET status='IN_FLIGHT', updated_at=? WHERE operation_id=?",
                    Timestamp.from(Instant.now()), normalizedOperationId);
            return operationResponse("DISPATCHED", false, findOperation(normalizedOperationId, false));
        });
    }

    @PostMapping("/jobs/{jobId}/operations/{operationId}/not-submitted")
    public Map<String, Object> markNotSubmitted(
            HttpServletRequest request,
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("NOT_SUBMITTED".equals(current)) return operationResponse("NOT_SUBMITTED", true, operation);
            if (!"PREPARED".equals(current)) {
                throw new RequestValidationException("RECONCILE_REQUIRED", "Only a prepared operation with durable proof of non-submission can be marked NOT_SUBMITTED.");
            }
            jdbc.update("UPDATE rpf_execution_operation SET status='NOT_SUBMITTED', updated_at=? WHERE operation_id=?",
                    Timestamp.from(Instant.now()), normalizedOperationId);
            return operationResponse("NOT_SUBMITTED", false, findOperation(normalizedOperationId, false));
        });
    }

    /** Probe-only simulated controlled effect used to prove fencing/reconcile. */
    @PostMapping("/jobs/{jobId}/operations/{operationId}/apply")
    public ResponseEntity<Map<String, Object>> apply(
            HttpServletRequest request,
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody,
            @RequestParam(name = "simulate_response_lost", defaultValue = "false") boolean simulateResponseLost
    ) {
        authService.require(request, "execution:worker");
        if (!probeEnabled) throw new RequestValidationException("PROBE_MODE_REQUIRED", "The simulated effect endpoint is disabled outside controlled probe mode.");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        Map<String, Object> result = transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("UNKNOWN_OUTCOME".equals(current) || "IN_FLIGHT".equals(current)) {
                throw new RequestValidationException("RECONCILE_REQUIRED", "The operation may have been submitted; reconcile before mutation retry.");
            }
            if ("CONFIRMED".equals(current)) return operationResponse("IDEMPOTENT_REPLAY", true, operation);
            if (!Set.of("PREPARED", "NOT_SUBMITTED").contains(current)) {
                throw new RequestValidationException("OPERATION_NOT_APPLYABLE", "The operation is not in a safe-to-submit state.");
            }
            Instant now = Instant.now();
            String receipt = "receipt-" + normalizedOperationId;
            jdbc.update("""
                    INSERT INTO rpf_simulated_effect(operation_id, job_id, environment_id, receipt_ref, applied_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (operation_id) DO NOTHING
                    """, normalizedOperationId, normalizedJobId, operation.get("environment_id"), receipt, Timestamp.from(now));
            int effectCount = count("SELECT COUNT(*) FROM rpf_simulated_effect WHERE operation_id=?", normalizedOperationId);
            jdbc.update("UPDATE rpf_execution_operation SET status='IN_FLIGHT', effect_count=?, updated_at=? WHERE operation_id=?",
                    effectCount, Timestamp.from(now), normalizedOperationId);
            Map<String, Object> sent = operationResponse("SENT", false, findOperation(normalizedOperationId, false));
            sent.put("receipt_available_after_confirm", true);
            return sent;
        });
        if (simulateResponseLost) {
            Map<String, Object> lost = new LinkedHashMap<>();
            lost.put("error", "TRANSPORT_RESPONSE_LOST");
            lost.put("retriable", true);
            lost.put("operation_id", normalizedOperationId);
            lost.put("unknown_outcome_required", true);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(lost);
        }
        return ResponseEntity.ok(result);
    }

    @PostMapping("/jobs/{jobId}/operations/{operationId}/confirm")
    public Map<String, Object> confirmOperation(
            HttpServletRequest request,
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("CONFIRMED".equals(current)) return operationResponse("IDEMPOTENT_REPLAY", true, operation);
            if (!"IN_FLIGHT".equals(current)) {
                throw new RequestValidationException("RECONCILE_REQUIRED", "Only an in-flight operation can be confirmed.");
            }
            String receipt = optionalText(body.get("receipt_ref"));
            if (!effectExists(normalizedOperationId) && receipt == null) {
                throw new RequestValidationException("RECONCILE_REQUIRED", "No receipt/effect proof is available to confirm this operation.");
            }
            if (receipt == null) {
                receipt = text(jdbc.queryForMap("SELECT receipt_ref FROM rpf_simulated_effect WHERE operation_id=?", normalizedOperationId), "receipt_ref");
            }
            jdbc.update("UPDATE rpf_execution_operation SET status='CONFIRMED', effect_count=?, receipt_ref=?, updated_at=? WHERE operation_id=?",
                    effectExists(normalizedOperationId) ? 1 : integerValue(operation.get("effect_count")), receipt, Timestamp.from(Instant.now()), normalizedOperationId);
            return operationResponse("CONFIRMED", false, findOperation(normalizedOperationId, false));
        });
    }

    @PostMapping("/jobs/{jobId}/operations/{operationId}/unknown")
    public Map<String, Object> markUnknownOutcome(
            HttpServletRequest request,
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        requiredId(body, "worker_id");
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        try (ObservabilityService.SpanScope ignored = observability.span("runproof.operation.unknown", Map.of(
                "runproof.job.id", normalizedJobId, "runproof.operation.id", normalizedOperationId
        ))) {
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("CONFIRMED".equals(current) || "NOT_SUBMITTED".equals(current)) return operationResponse("ALREADY_RESOLVED", true, operation);
            if (!Set.of("PREPARED", "IN_FLIGHT").contains(current)) {
                throw new RequestValidationException("OPERATION_NOT_UNKNOWNABLE", "This operation cannot enter UNKNOWN_OUTCOME from its current state.");
            }
            Instant now = Instant.now();
            jdbc.update("UPDATE rpf_execution_operation SET status='UNKNOWN_OUTCOME', updated_at=? WHERE operation_id=?",
                    Timestamp.from(now), normalizedOperationId);
            String attemptId = text(operation, "attempt_id");
            if (attemptId != null) jdbc.update("UPDATE rpf_execution_attempt SET status='RECONCILE_REQUIRED', ended_at=?, reason=? WHERE attempt_id=?",
                    Timestamp.from(now), "UNKNOWN_OUTCOME", attemptId);
            String currentJobState = text(job, "state");
            if ("CANCEL_REQUESTED".equals(currentJobState)) {
                // Preserve the active fencing tuple so the current worker can
                // reconcile the uncertain operation and acknowledge cancel.
                long nextVersion = version(job) + 1;
                jdbc.update("""
                        UPDATE rpf_execution_job
                        SET state='CANCEL_REQUESTED', version=?, outcome_status=NULL, platform_reason=?,
                            last_operation_id=?, updated_at=?
                        WHERE job_id=?
                        """, nextVersion, "UNKNOWN_OUTCOME", normalizedOperationId, Timestamp.from(now), normalizedJobId);
                insertEvent(normalizedJobId, currentJobState, "CANCEL_REQUESTED", "UNKNOWN_OUTCOME", attemptId, normalizedOperationId,
                        nextVersion, "RECONCILE_BEFORE_CANCEL_ACK", now);
            } else if (!TERMINAL_STATES.contains(currentJobState) && !"RECONCILE_REQUIRED".equals(currentJobState)) {
                long nextVersion = version(job) + 1;
                updateStateClear(job, "RECONCILE_REQUIRED", nextVersion, "UNKNOWN_OUTCOME", null, null, normalizedOperationId);
                insertEvent(normalizedJobId, text(job, "state"), "RECONCILE_REQUIRED", "UNKNOWN_OUTCOME", attemptId, normalizedOperationId, nextVersion, "RECONCILE_BEFORE_RETRY", now);
            } else if ("RECONCILE_REQUIRED".equals(currentJobState)) {
                insertEvent(normalizedJobId, "RECONCILE_REQUIRED", "RECONCILE_REQUIRED", "UNKNOWN_OUTCOME", attemptId, normalizedOperationId, version(job), "RECONCILE_BEFORE_RETRY", now);
            }
            return operationResponse("UNKNOWN_OUTCOME", false, findOperation(normalizedOperationId, false));
        });
        }
    }

    @PostMapping("/jobs/{jobId}/operations/{operationId}/reconcile")
    public Map<String, Object> reconcile(
            HttpServletRequest request,
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        requiredId(body, "worker_id");
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        try (ObservabilityService.SpanScope ignored = observability.span("runproof.operation.reconcile", Map.of(
                "runproof.job.id", normalizedJobId, "runproof.operation.id", normalizedOperationId
        ))) {
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("CONFIRMED".equals(current)) return reconcileResponse("CONFIRMED", false, true, operation, job);
            if ("NOT_SUBMITTED".equals(current)) return reconcileResponse("NOT_SUBMITTED", true, true, operation, job);
            if (!Set.of("UNKNOWN_OUTCOME", "IN_FLIGHT", "PREPARED").contains(current)) {
                throw new RequestValidationException("OPERATION_NOT_RECONCILABLE", "The operation has no unresolved outcome to reconcile.");
            }
            boolean effect = effectExists(normalizedOperationId);
            String nextStatus = effect ? "CONFIRMED" : "NOT_SUBMITTED";
            String receipt = effect ? text(jdbc.queryForMap("SELECT receipt_ref FROM rpf_simulated_effect WHERE operation_id=?", normalizedOperationId), "receipt_ref") : null;
            jdbc.update("UPDATE rpf_execution_operation SET status=?, effect_count=?, receipt_ref=?, updated_at=? WHERE operation_id=?",
                    nextStatus, effect ? 1 : 0, receipt, Timestamp.from(Instant.now()), normalizedOperationId);
            String attemptId = text(operation, "attempt_id");
            if (attemptId != null) jdbc.update("UPDATE rpf_execution_attempt SET status='RECONCILED', ended_at=?, reason=? WHERE attempt_id=?",
                    Timestamp.from(Instant.now()), "RECONCILED_" + nextStatus, attemptId);
            String currentJobState = text(job, "state");
            if (!TERMINAL_STATES.contains(currentJobState)) {
                long nextVersion = version(job) + 1;
                if ("CANCEL_REQUESTED".equals(currentJobState)) {
                    // Keep the active fencing tuple available for the worker's
                    // safe cancellation acknowledgement. Reconcile resolves
                    // the operation; it does not silently turn a cancellation
                    // request back into ordinary queued work.
                    jdbc.update("""
                            UPDATE rpf_execution_job
                                SET state='CANCEL_REQUESTED', version=?, outcome_status=NULL, platform_reason=?,
                                last_operation_id=?, updated_at=?
                            WHERE job_id=?
                            """, nextVersion, "RECONCILED_" + nextStatus, normalizedOperationId, Timestamp.from(Instant.now()), normalizedJobId);
                } else {
                    updateStateClear(job, "QUEUED", nextVersion, "RECONCILED_" + nextStatus, null, null, normalizedOperationId);
                }
                insertEvent(normalizedJobId, currentJobState, "CANCEL_REQUESTED".equals(currentJobState) ? "CANCEL_REQUESTED" : "QUEUED",
                        "OPERATION_RECONCILED", attemptId, normalizedOperationId, nextVersion, nextStatus, Instant.now());
            }
            return reconcileResponse(nextStatus, "NOT_SUBMITTED".equals(nextStatus), false, findOperation(normalizedOperationId, false), findJob(normalizedJobId, false, true));
        });
        }
    }

    @GetMapping("/jobs/{jobId}/operations/{operationId}")
    public Map<String, Object> getOperation(
            HttpServletRequest request,
            @PathVariable String jobId,
            @PathVariable String operationId
    ) {
        authService.require(request, "metadata:read");
        return operationResponse("READ", false, ownedOperation(
                requiredIdValue(jobId, "job_id"), requiredIdValue(operationId, "operation_id"), false));
    }

    @PostMapping("/jobs/{jobId}/evidence")
    public Map<String, Object> ingestEvidence(
            HttpServletRequest request,
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String evidenceId = requiredId(body, "evidence_id");
        String entityType = requiredId(body, "entity_type").toUpperCase(Locale.ROOT);
        String entityId = requiredId(body, "entity_id");
        String outcome = requiredId(body, "outcome").toUpperCase(Locale.ROOT);
        String contentSha = requiredId(body, "content_sha256").toLowerCase(Locale.ROOT);
        Map<String, Object> artifactRef = object(body.get("artifact_ref"), "artifact_ref");
        Map<String, Object> safeEvidence = new LinkedHashMap<>(body);
        // Lease credentials are accepted only as transient fencing inputs;
        // they are never included in the persisted evidence payload.
        safeEvidence.remove("attempt_id");
        safeEvidence.remove("worker_id");
        safeEvidence.remove("lease_token");
        safeEvidence.remove("lease_version");
        ensureSafe(safeEvidence);
        if (!EVIDENCE_TYPES.contains(entityType) || !EVIDENCE_OUTCOMES.contains(outcome)) {
            throw new RequestValidationException("INVALID_EVIDENCE_CONTRACT", "Execution evidence type or outcome is outside the RunProof contract.");
        }
        if (Set.of("RELEASE_DECISION", "STATISTICAL_RELEASE_DECISION").contains(entityType)) {
            throw new ProbeExceptions.AuthorizationForbiddenException("decision:write");
        }
        if (!contentSha.matches("[0-9a-f]{64}")) {
            throw new RequestValidationException("INVALID_EVIDENCE_FINGERPRINT", "Execution evidence content_sha256 must be a SHA-256 fingerprint.");
        }
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            String attemptId = null;
            if (OWNER_STATES.contains(text(job, "state"))) {
                requireOwner(job, body);
                attemptId = text(job, "active_attempt_id");
            } else if (!"QUEUED".equals(text(job, "state"))) {
                throw new RequestValidationException("EVIDENCE_NOT_ACCEPTED_AT_BOUNDARY", "Execution evidence is accepted only for a queued job or its active owner attempt.");
            }
            Map<String, Object> byId = findEvidence(evidenceId, true);
            Map<String, Object> byNaturalKey = findEvidenceByNaturalKey(normalizedJobId, entityType, entityId, true);
            Map<String, Object> existing = byId != null ? byId : byNaturalKey;
            if (existing != null) {
                if (!Objects.equals(existing.get("content_sha256"), contentSha)
                        || !Objects.equals(existing.get("entity_type"), entityType)
                        || !Objects.equals(existing.get("entity_id"), entityId)
                        || !Objects.equals(existing.get("job_id"), normalizedJobId)
                        || !Objects.equals(existing.get("attempt_id"), attemptId)) {
                    throw new IdentityConflictException("IMMUTABLE_EVIDENCE_CONFLICT", "Evidence identity already exists with different immutable content.");
                }
                return evidenceResponse("IDEMPOTENT_REPLAY", true, existing);
            }
            Instant now = Instant.now();
            int inserted = jdbc.update("""
                    INSERT INTO rpf_execution_evidence(
                        evidence_id, job_id, attempt_id, entity_type, entity_id, outcome, content_sha256, artifact_ref_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """, evidenceId, normalizedJobId, attemptId, entityType, entityId, outcome, contentSha, json(artifactRef), Timestamp.from(now));
            if (inserted == 0) {
                Map<String, Object> winner = findEvidence(evidenceId, true);
                if (winner == null) winner = findEvidenceByNaturalKey(normalizedJobId, entityType, entityId, true);
                if (winner == null || !Objects.equals(winner.get("content_sha256"), contentSha)
                        || !Objects.equals(winner.get("attempt_id"), attemptId)) {
                    throw new IdentityConflictException("IMMUTABLE_EVIDENCE_CONFLICT", "Concurrent evidence ingest produced a different immutable winner.");
                }
                return evidenceResponse("IDEMPOTENT_REPLAY", true, winner);
            }
            insertEvent(normalizedJobId, text(job, "state"), text(job, "state"),
                    "EVIDENCE_INGESTED", attemptId, null, version(job), "IMMUTABLE_REF_STORED", now);
            return evidenceResponse("EVIDENCE_STORED", false, findEvidence(evidenceId, false));
        });
    }

    @PostMapping("/jobs/{jobId}/complete")
    public Map<String, Object> complete(
            HttpServletRequest request,
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String evidenceId = requiredId(body, "evidence_id");
        try (ObservabilityService.SpanScope ignored = observability.span("runproof.job.terminalize", Map.of("runproof.job.id", normalizedJobId, "runproof.outcome", "COMPLETED"))) {
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            if ("COMPLETED".equals(job.get("state")) && Objects.equals(job.get("terminal_evidence_id"), evidenceId)) {
                return response("IDEMPOTENT_REPLAY", true, normalizedJobId, snapshot(job));
            }
            requireOwner(job, body);
            if (!Set.of("CLAIMED", "RUNNING").contains(text(job, "state"))) {
                throw new RequestValidationException("JOB_NOT_COMPLETABLE", "Only a claimed/running attempt can complete a job.");
            }
            Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
            if (hasUnsafeOperation(normalizedJobId)) {
                throw new RequestValidationException("RECONCILE_REQUIRED", "Completion is blocked until every unresolved operation is reconciled.");
            }
            requireVerifiedTerminalEvidence(job, evidence);
            finishTerminal(job, "COMPLETED", "COMPLETED", text(evidence, "outcome"), evidenceId, "EVIDENCE_COMMITTED", "ATTEMPT_COMPLETED");
            return response("COMPLETED", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
        });
        }
    }

    @PostMapping("/jobs/{jobId}/fail-platform")
    public Map<String, Object> failPlatform(
            HttpServletRequest request,
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String evidenceId = requiredId(body, "evidence_id");
        String reason = requiredId(body, "reason");
        try (ObservabilityService.SpanScope ignored = observability.span("runproof.job.terminalize", Map.of("runproof.job.id", normalizedJobId, "runproof.outcome", "FAILED_PLATFORM"))) {
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
            if (!Set.of("ERROR", "INCONCLUSIVE").contains(text(evidence, "outcome"))) {
                throw new RequestValidationException("PLATFORM_FAILURE_EVIDENCE_REQUIRED", "Platform failure must use ERROR or INCONCLUSIVE evidence.");
            }
            finishTerminal(job, "FAILED_PLATFORM", "FAILED_PLATFORM", text(evidence, "outcome"), evidenceId, reason, "ATTEMPT_FAILED_PLATFORM");
            return response("FAILED_PLATFORM", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
        });
        }
    }

    @PostMapping("/jobs/{jobId}/cancel")
    public Map<String, Object> cancel(
            HttpServletRequest request,
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.requireAny(request, "execution:submit", "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            String state = text(job, "state");
            if (TERMINAL_STATES.contains(state)) return response("TERMINAL", true, normalizedJobId, snapshot(job));
            if ("QUEUED".equals(state)) {
                String evidenceId = requiredId(body, "evidence_id");
                Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
                if (!"CANCELLED".equals(text(evidence, "outcome"))) {
                    throw new RequestValidationException("CANCELLATION_EVIDENCE_REQUIRED", "Queued cancellation requires CANCELLED evidence.");
                }
                finishTerminal(job, "CANCELLED", "CANCELLED", "CANCELLED", evidenceId, "QUEUED_CANCELLED", "JOB_CANCELLED");
                return response("CANCELLED", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
            }
            if ("CANCEL_REQUESTED".equals(state)) return response("CANCEL_REQUESTED", true, normalizedJobId, snapshot(job));
            if (!OWNER_STATES.contains(state)) throw new RequestValidationException("JOB_NOT_CANCELLABLE", "The job is not at a cancellable execution boundary.");
            Instant now = Instant.now();
            long nextVersion = version(job) + 1;
            jdbc.update("UPDATE rpf_execution_job SET state='CANCEL_REQUESTED', cancel_requested=TRUE, version=?, updated_at=? WHERE job_id=?",
                    nextVersion, Timestamp.from(now), normalizedJobId);
            jdbc.update("UPDATE rpf_execution_attempt SET lease_version=? WHERE attempt_id=?", nextVersion, job.get("active_attempt_id"));
            insertEvent(normalizedJobId, state, "CANCEL_REQUESTED", "CANCELLATION_REQUESTED", text(job, "active_attempt_id"), null, nextVersion, "WAIT_FOR_WORKER_ACK", now);
            return response("CANCEL_REQUESTED", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
        });
    }

    @PostMapping("/jobs/{jobId}/cancel/ack")
    public Map<String, Object> acknowledgeCancel(
            HttpServletRequest request,
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.require(request, "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String evidenceId = requiredId(body, "evidence_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            if (!"CANCEL_REQUESTED".equals(job.get("state"))) throw new RequestValidationException("CANCEL_NOT_REQUESTED", "Cancellation acknowledgement requires CANCEL_REQUESTED state.");
            if (hasUnsafeOperation(normalizedJobId)) throw new RequestValidationException("RECONCILE_REQUIRED", "Cancellation cannot finalize while a side effect has unresolved outcome.");
            Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
            if (!"CANCELLED".equals(text(evidence, "outcome"))) throw new RequestValidationException("CANCELLATION_EVIDENCE_REQUIRED", "Cancellation acknowledgement requires CANCELLED evidence.");
            finishTerminal(job, "CANCELLED", "CANCELLED", "CANCELLED", evidenceId, "WORKER_ACKNOWLEDGED", "ATTEMPT_CANCELLED");
            return response("CANCELLED", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
        });
    }

    @PostMapping("/jobs/{jobId}/timeout")
    public Map<String, Object> timeout(
            HttpServletRequest request,
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        authService.requireAny(request, "execution:submit", "execution:worker");
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String evidenceId = requiredId(body, "evidence_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            String state = text(job, "state");
            if (TERMINAL_STATES.contains(state)) return response("TERMINAL", true, normalizedJobId, snapshot(job));
            if ("QUEUED".equals(state)) {
                Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
                requirePlatformOutcome(evidence);
                finishTerminal(job, "FAILED_PLATFORM", "FAILED_PLATFORM", text(evidence, "outcome"), evidenceId, "TIMEOUT_BEFORE_START", "JOB_TIMEOUT_PLATFORM");
                return response("FAILED_PLATFORM", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
            }
            if (OWNER_STATES.contains(state)) {
                requireOwner(job, body);
                if (hasUnsafeOperation(normalizedJobId)) {
                    String attemptId = text(job, "active_attempt_id");
                    Instant now = Instant.now();
                    long nextVersion = version(job) + 1;
                    jdbc.update("UPDATE rpf_execution_attempt SET status='RECONCILE_REQUIRED', ended_at=?, reason=? WHERE attempt_id=?", Timestamp.from(now), "TIMEOUT_RECONCILE_REQUIRED", attemptId);
                    updateStateClear(job, "RECONCILE_REQUIRED", nextVersion, "TIMEOUT_RECONCILE_REQUIRED", null, null, text(job, "last_operation_id"));
                    insertEvent(normalizedJobId, state, "RECONCILE_REQUIRED", "TIMEOUT_RECONCILE_REQUIRED", attemptId, text(job, "last_operation_id"), nextVersion, "NO_BLIND_AGENT_FAIL", now);
                    return response("RECONCILE_REQUIRED", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
                }
                Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
                requirePlatformOutcome(evidence);
                finishTerminal(job, "FAILED_PLATFORM", "FAILED_PLATFORM", text(evidence, "outcome"), evidenceId, "TIMEOUT_SAFE_BOUNDARY", "JOB_TIMEOUT_PLATFORM");
                return response("FAILED_PLATFORM", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
            }
            throw new RequestValidationException("JOB_NOT_TIMEOUTABLE", "The job is not at an executable timeout boundary.");
        });
    }

    private Map<String, Object> claimLocked(String jobId, String workerId, int leaseSeconds) {
        Map<String, Object> job = findJob(jobId, true, true);
        String state = text(job, "state");
        if (TERMINAL_STATES.contains(state)) return response("TERMINAL", false, jobId, snapshot(job));
        if ("RECONCILE_REQUIRED".equals(state)) return response("RECONCILE_REQUIRED", false, jobId, snapshot(job));
        if ("CANCEL_REQUESTED".equals(state)) return response("CANCEL_REQUESTED", false, jobId, snapshot(job));
        String activeAttempt = text(job, "active_attempt_id");
        String previousAttemptContext = null;
        if (activeAttempt != null) {
            previousAttemptContext = text(jdbc.queryForMap("SELECT otel_context_json FROM rpf_execution_attempt WHERE attempt_id=?", activeAttempt), "otel_context_json");
            boolean expired = Boolean.TRUE.equals(jdbc.queryForObject("SELECT lease_expires_at <= CURRENT_TIMESTAMP FROM rpf_execution_job WHERE job_id=?", Boolean.class, jobId));
            if (!expired) throw new IdentityConflictException("ACTIVE_LEASE", "Another worker currently owns the job lease.");
            Instant now = Instant.now();
            if (hasUnsafeOperationForAttempt(activeAttempt)) {
                jdbc.update("UPDATE rpf_execution_attempt SET status='RECONCILE_REQUIRED', ended_at=?, reason=? WHERE attempt_id=?", Timestamp.from(now), "LEASE_EXPIRED_RECONCILE_REQUIRED", activeAttempt);
                long nextVersion = version(job) + 1;
                updateStateClear(job, "RECONCILE_REQUIRED", nextVersion, "LEASE_EXPIRED_RECONCILE_REQUIRED", null, null, text(job, "last_operation_id"));
                insertEvent(jobId, state, "RECONCILE_REQUIRED", "LEASE_EXPIRED_REQUIRES_RECONCILE", activeAttempt, text(job, "last_operation_id"), nextVersion, "LEASE_EXPIRY_IS_NOT_PROOF_OF_NON_EXECUTION", now);
                return response("RECONCILE_REQUIRED", false, jobId, snapshot(findJob(jobId, false, true)));
            }
            jdbc.update("UPDATE rpf_execution_attempt SET status='EXPIRED', ended_at=?, reason=? WHERE attempt_id=?", Timestamp.from(now), "LEASE_EXPIRED_SAFE_TO_RECLAIM", activeAttempt);
            long nextVersion = version(job) + 1;
            updateStateClear(job, "QUEUED", nextVersion, "LEASE_EXPIRED_SAFE_TO_RECLAIM", null, null, text(job, "last_operation_id"));
            insertEvent(jobId, state, "QUEUED", "LEASE_EXPIRED_REQUEUED", activeAttempt, null, nextVersion, "NO_UNCERTAIN_SIDE_EFFECT", now);
            job = findJob(jobId, true, true);
        }
        if (!"QUEUED".equals(job.get("state"))) throw new RequestValidationException("JOB_NOT_CLAIMABLE", "The job is not queued for a new attempt.");
        Instant now = Instant.now();
        Instant expires = now.plusSeconds(leaseSeconds);
        String attemptId = "attempt-" + UUID.randomUUID();
        String leaseToken = UUID.randomUUID() + UUID.randomUUID().toString();
        long nextVersion = version(job) + 1;
        int attemptNumber = integerValue(job.get("attempt_number")) + 1;
        String tokenHash = sha256(leaseToken);
        jdbc.update("""
                INSERT INTO rpf_execution_attempt(
                    attempt_id, job_id, attempt_number, worker_id, lease_token_hash, lease_version,
                    status, lease_expires_at, otel_context_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'CLAIMED', ?, NULL, ?)
                """, attemptId, jobId, attemptNumber, workerId, tokenHash, nextVersion, Timestamp.from(expires), Timestamp.from(now));
        jdbc.update("""
                UPDATE rpf_execution_job
                SET state='CLAIMED', version=?, attempt_number=?, active_attempt_id=?, active_worker_id=?,
                    active_lease_token_hash=?, lease_expires_at=?, heartbeat_at=?, updated_at=?
                WHERE job_id=?
                """, nextVersion, attemptNumber, attemptId, workerId, tokenHash, Timestamp.from(expires), Timestamp.from(now), Timestamp.from(now), jobId);
        insertEvent(jobId, "QUEUED", "CLAIMED", "JOB_CLAIMED", attemptId, null, nextVersion, "POLL_CLAIM", now);
        Map<String, Object> updated = findJob(jobId, false, true);
        Map<String, Object> result = response("CLAIMED", false, jobId, snapshot(updated));
        result.put("lease", leaseDetails(updated, leaseToken, nextVersion, expires));
        Map<String, Object> observabilityContext = new LinkedHashMap<>();
        observabilityContext.put("schema_version", ObservabilityService.CONTEXT_SCHEMA);
        observabilityContext.put("job", parseJson(text(updated, "otel_context_json")));
        if (previousAttemptContext != null && !previousAttemptContext.isBlank()) {
            observabilityContext.put("previous_attempt", parseJson(previousAttemptContext));
        }
        result.put("observability_context", observabilityContext);
        return result;
    }

    private void finishTerminal(Map<String, Object> job, String state, String attemptStatus, String outcome, String evidenceId, String reason, String eventType) {
        String jobId = text(job, "job_id");
        String attemptId = text(job, "active_attempt_id");
        Instant now = Instant.now();
        long nextVersion = version(job) + 1;
        if (attemptId != null) jdbc.update("UPDATE rpf_execution_attempt SET status=?, ended_at=?, reason=? WHERE attempt_id=?", attemptStatus, Timestamp.from(now), reason, attemptId);
        updateStateClear(job, state, nextVersion, reason, outcome, evidenceId, text(job, "last_operation_id"));
        insertEvent(jobId, text(job, "state"), state, eventType, attemptId, null, nextVersion, reason, now);
    }

    private void updateStateClear(Map<String, Object> oldJob, String state, long version, String reason, String outcome, String evidenceId, String operationId) {
        jdbc.update("""
                UPDATE rpf_execution_job
                SET state=?, version=?, active_attempt_id=NULL, active_worker_id=NULL,
                    active_lease_token_hash=NULL, lease_expires_at=NULL, heartbeat_at=NULL,
                    outcome_status=?, platform_reason=?, terminal_evidence_id=?, last_operation_id=?, updated_at=?
                WHERE job_id=?
                """, state, version, outcome, reason, evidenceId, operationId, Timestamp.from(Instant.now()), oldJob.get("job_id"));
    }

    private void requireOwner(Map<String, Object> job, Map<String, Object> body) {
        String state = text(job, "state");
        if (!OWNER_STATES.contains(state)) throw new IdentityConflictException("STALE_ATTEMPT", "The job no longer has an active owner attempt.");
        String expectedAttempt = text(job, "active_attempt_id");
        String expectedWorker = text(job, "active_worker_id");
        String attempt = requiredId(body, "attempt_id");
        String worker = requiredId(body, "worker_id");
        String token = requiredId(body, "lease_token");
        long leaseVersion = requiredLong(body, "lease_version");
        boolean expired = Boolean.TRUE.equals(jdbc.queryForObject(
                "SELECT lease_expires_at IS NULL OR lease_expires_at <= CURRENT_TIMESTAMP FROM rpf_execution_job WHERE job_id=?",
                Boolean.class, job.get("job_id")
        ));
        if (expired || !Objects.equals(expectedAttempt, attempt) || !Objects.equals(expectedWorker, worker)
                || leaseVersion != version(job) || !Objects.equals(text(job, "active_lease_token_hash"), sha256(token))) {
            throw new IdentityConflictException("STALE_ATTEMPT", "Attempt fencing rejected a stale or non-owner mutation.");
        }
    }

    private Map<String, Object> leaseDetails(Map<String, Object> job, Object rawToken, long version, Instant expires) {
        Map<String, Object> lease = new LinkedHashMap<>();
        lease.put("attempt_id", job.get("active_attempt_id"));
        lease.put("worker_id", job.get("active_worker_id"));
        lease.put("lease_version", version);
        lease.put("lease_expires_at", expires == null ? job.get("lease_expires_at") : expires.toString());
        if (rawToken instanceof String token && !token.isBlank()) lease.put("lease_token", token);
        lease.put("lease_token_present", job.get("active_lease_token_hash") != null);
        return lease;
    }

    private Map<String, Object> snapshot(Map<String, Object> job) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("job_id", job.get("job_id"));
        result.put("idempotency_key", job.get("idempotency_key"));
        result.put("request_fingerprint", job.get("request_fingerprint"));
        result.put("job_type", job.get("job_type"));
        result.put("target", Map.of("type", job.get("target_type"), "id", job.get("target_id")));
        result.put("correlation_id", job.get("correlation_id"));
        result.put("state", job.get("state"));
        result.put("version", job.get("version"));
        result.put("attempt_number", job.get("attempt_number"));
        result.put("active_attempt_id", job.get("active_attempt_id"));
        result.put("active_worker_id", job.get("active_worker_id"));
        result.put("lease", leaseDetails(job, null, version(job), null));
        result.put("cancel_requested", job.get("cancel_requested"));
        result.put("timeout_requested", job.get("timeout_requested"));
        result.put("outcome_status", job.get("outcome_status"));
        result.put("platform_reason", job.get("platform_reason"));
        result.put("terminal_evidence_id", job.get("terminal_evidence_id"));
        result.put("last_operation_id", job.get("last_operation_id"));
        result.put("payload_ref", parseJson(text(job, "payload_ref_json")));
        result.put("created_at", job.get("created_at"));
        result.put("updated_at", job.get("updated_at"));
        List<Map<String, Object>> attempts = new ArrayList<>();
        for (Map<String, Object> attempt : jdbc.queryForList("""
                SELECT attempt_id, attempt_number, worker_id, lease_version, status,
                       lease_expires_at::text AS lease_expires_at, heartbeat_at::text AS heartbeat_at,
                       started_at::text AS started_at, ended_at::text AS ended_at, reason, created_at::text AS created_at
                FROM rpf_execution_attempt WHERE job_id=? ORDER BY attempt_number
                """, job.get("job_id"))) attempts.add(new LinkedHashMap<>(attempt));
        result.put("attempts", attempts);
        List<Map<String, Object>> operations = new ArrayList<>();
        for (Map<String, Object> operation : jdbc.queryForList("""
                SELECT operation_id, attempt_id, environment_id, operation_fingerprint, status, effect_count, receipt_ref,
                       created_at::text AS created_at, updated_at::text AS updated_at
                FROM rpf_execution_operation WHERE job_id=? ORDER BY created_at, operation_id
                """, job.get("job_id"))) operations.add(new LinkedHashMap<>(operation));
        result.put("operations", operations);
        List<Map<String, Object>> evidence = new ArrayList<>();
        for (Map<String, Object> item : jdbc.queryForList("""
                SELECT evidence_id, attempt_id, entity_type, entity_id, outcome, content_sha256, artifact_ref_json,
                       created_at::text AS created_at
                FROM rpf_execution_evidence WHERE job_id=? ORDER BY created_at, evidence_id
                """, job.get("job_id"))) {
            Map<String, Object> copy = new LinkedHashMap<>(item);
            copy.put("artifact_ref", parseJson(text(item, "artifact_ref_json")));
            copy.remove("artifact_ref_json");
            evidence.add(copy);
        }
        result.put("evidence", evidence);
        result.put("events", jdbc.queryForList("""
                SELECT event_id, from_state, to_state, event_type, attempt_id, operation_id, reason, version,
                       occurred_at::text AS occurred_at
                FROM rpf_execution_event WHERE job_id=? ORDER BY event_id
                """, job.get("job_id")));
        return result;
    }

    private Map<String, Object> findJob(String jobId, boolean forUpdate, boolean throwIfMissing) {
        String sql = """
                SELECT job_id, idempotency_key, request_fingerprint, job_type, target_type, target_id,
                       payload_ref_json, correlation_id, state, version, attempt_number,
                       active_attempt_id, active_worker_id, active_lease_token_hash,
                       lease_expires_at::text AS lease_expires_at, heartbeat_at::text AS heartbeat_at,
                       cancel_requested, timeout_requested, outcome_status, platform_reason,
                       terminal_evidence_id, last_operation_id, otel_context_json, created_at::text AS created_at,
                       updated_at::text AS updated_at
                FROM rpf_execution_job WHERE job_id=?
                """ + (forUpdate ? " FOR UPDATE" : "");
        try {
            return jdbc.queryForMap(sql, jobId);
        } catch (EmptyResultDataAccessException exception) {
            if (throwIfMissing) throw new EntityNotFoundException("Durable job does not exist: " + jobId);
            return null;
        }
    }

    private Map<String, Object> findJobByIdempotency(String idempotencyKey, boolean forUpdate) {
        String sql = "SELECT job_id FROM rpf_execution_job WHERE idempotency_key=?" + (forUpdate ? " FOR UPDATE" : "");
        List<Map<String, Object>> rows = jdbc.queryForList(sql, idempotencyKey);
        return rows.isEmpty() ? null : findJob(text(rows.get(0), "job_id"), forUpdate, true);
    }

    private Map<String, Object> findOperation(String operationId, boolean forUpdate) {
        String sql = """
                SELECT operation_id, job_id, attempt_id, environment_id, operation_fingerprint, status,
                       effect_count, receipt_ref, created_at::text AS created_at, updated_at::text AS updated_at
                FROM rpf_execution_operation WHERE operation_id=?
                """ + (forUpdate ? " FOR UPDATE" : "");
        List<Map<String, Object>> rows = jdbc.queryForList(sql, operationId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private Map<String, Object> ownedOperation(String jobId, String operationId, boolean forUpdate) {
        Map<String, Object> operation = findOperation(operationId, forUpdate);
        if (operation == null || !Objects.equals(operation.get("job_id"), jobId)) throw new EntityNotFoundException("Durable operation does not exist for this job: " + operationId);
        return operation;
    }

    private Map<String, Object> findEvidence(String evidenceId, boolean forUpdate) {
        String sql = """
                SELECT evidence_id, job_id, attempt_id, entity_type, entity_id, outcome, content_sha256, artifact_ref_json,
                       created_at::text AS created_at
                FROM rpf_execution_evidence WHERE evidence_id=?
                """ + (forUpdate ? " FOR UPDATE" : "");
        List<Map<String, Object>> rows = jdbc.queryForList(sql, evidenceId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private Map<String, Object> findEvidenceByNaturalKey(String jobId, String entityType, String entityId, boolean forUpdate) {
        String sql = """
                SELECT evidence_id, job_id, attempt_id, entity_type, entity_id, outcome, content_sha256, artifact_ref_json,
                       created_at::text AS created_at
                FROM rpf_execution_evidence WHERE job_id=? AND entity_type=? AND entity_id=?
                """ + (forUpdate ? " FOR UPDATE" : "");
        List<Map<String, Object>> rows = jdbc.queryForList(sql, jobId, entityType, entityId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private Map<String, Object> evidenceForJob(String jobId, String evidenceId, boolean forUpdate) {
        Map<String, Object> evidence = findEvidence(evidenceId, forUpdate);
        if (evidence == null || !Objects.equals(evidence.get("job_id"), jobId)) throw new EntityNotFoundException("Evidence does not exist for this durable job: " + evidenceId);
        return evidence;
    }

    private void requireVerifiedTerminalEvidence(Map<String, Object> job, Map<String, Object> evidence) {
        if (!Objects.equals(text(job, "active_attempt_id"), text(evidence, "attempt_id"))) {
            throw new IdentityConflictException("STALE_ATTEMPT", "Terminal evidence belongs to a different execution attempt.");
        }
        if (!"PASS".equals(text(evidence, "outcome"))) {
            throw new RequestValidationException("TERMINAL_EVIDENCE_PASS_REQUIRED", "A completed durable job requires PASS execution evidence.");
        }
        Object storedReference = evidence.get("artifact_ref");
        if (!(storedReference instanceof Map<?, ?>)) {
            storedReference = parseJson(text(evidence, "artifact_ref_json"));
        }
        Map<String, Object> referenceMap = object(storedReference, "artifact_ref");
        ApiModels.ArtifactRef evidenceReference;
        try {
            evidenceReference = mapper.convertValue(referenceMap, ApiModels.ArtifactRef.class);
        } catch (IllegalArgumentException exception) {
            throw new InvalidEvidenceException("INVALID_TERMINAL_ARTIFACT_REF", "Terminal evidence artifact reference is malformed.");
        }
        if (evidenceReference == null
                || !Objects.equals(text(evidence, "content_sha256"), evidenceReference.contentSha256())
                || evidenceReference.artifactId() == null
                || evidenceReference.artifactKey() == null
                || evidenceReference.artifactKind() == null
                || evidenceReference.schemaVersion() == null
                || evidenceReference.sourceSha256() == null
                || evidenceReference.runtimeVersion() == null) {
            throw new InvalidEvidenceException("INVALID_TERMINAL_ARTIFACT_REF", "Terminal evidence artifact reference does not match its immutable content identity.");
        }
        ApiModels.ArtifactResponse canonical;
        try {
            canonical = canonicalMetadataService.readArtifact(text(evidence, "entity_type"), text(evidence, "entity_id"));
        } catch (EntityNotFoundException exception) {
            throw new InvalidEvidenceException("TERMINAL_ARTIFACT_NOT_REGISTERED", "Terminal evidence must reference a registered canonical artifact.");
        }
        ApiModels.ArtifactSnapshot snapshot = canonical == null ? null : canonical.artifactRef();
        if (snapshot == null || !snapshot.resolved()
                || !Objects.equals(evidenceReference.artifactId(), snapshot.artifactId())
                || !Objects.equals(evidenceReference.artifactKey(), snapshot.artifactKey())
                || !Objects.equals(evidenceReference.artifactKind(), snapshot.artifactKind())
                || !Objects.equals(evidenceReference.schemaVersion(), snapshot.schemaVersion())
                || !evidenceReference.contentSha256().equalsIgnoreCase(snapshot.contentSha256())
                || !Objects.equals(evidenceReference.sourceSha256(), snapshot.sourceSha256())
                || !Objects.equals(evidenceReference.runtimeVersion(), snapshot.runtimeVersion())) {
            throw new InvalidEvidenceException("INVALID_TERMINAL_ARTIFACT_REF", "Terminal evidence does not resolve to the registered immutable artifact.");
        }
    }

    private boolean hasUnsafeOperation(String jobId) {
        return count("SELECT COUNT(*) FROM rpf_execution_operation WHERE job_id=? AND status IN ('PREPARED','IN_FLIGHT','UNKNOWN_OUTCOME')", jobId) > 0;
    }

    private boolean hasUnsafeOperationForAttempt(String attemptId) {
        return count("SELECT COUNT(*) FROM rpf_execution_operation WHERE attempt_id=? AND status IN ('PREPARED','IN_FLIGHT','UNKNOWN_OUTCOME')", attemptId) > 0;
    }

    private boolean effectExists(String operationId) {
        return count("SELECT COUNT(*) FROM rpf_simulated_effect WHERE operation_id=?", operationId) > 0;
    }

    private void requirePlatformOutcome(Map<String, Object> evidence) {
        if (!Set.of("ERROR", "INCONCLUSIVE").contains(text(evidence, "outcome"))) throw new RequestValidationException("PLATFORM_FAILURE_EVIDENCE_REQUIRED", "Timeout/platform failure must use ERROR or INCONCLUSIVE evidence.");
    }

    private void insertEvent(String jobId, String fromState, String toState, String eventType, String attemptId, String operationId, long version, String reason, Instant occurredAt) {
        jdbc.update("""
                INSERT INTO rpf_execution_event(job_id, from_state, to_state, event_type, attempt_id, operation_id, reason, version, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, jobId, fromState, toState, eventType, attemptId, operationId, reason, version, Timestamp.from(occurredAt));
    }

    private static Map<String, Object> response(String status, boolean alreadyExists, Object jobId, Map<String, Object> job) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", status);
        result.put("already_exists", alreadyExists);
        result.put("job_id", jobId);
        result.put("job", job);
        return result;
    }

    private static Map<String, Object> operationResponse(String status, boolean alreadyExists, Map<String, Object> operation) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", status);
        result.put("already_exists", alreadyExists);
        result.put("operation", operation);
        return result;
    }

    private Map<String, Object> reconcileResponse(String status, boolean safeToRetry, boolean alreadyExists, Map<String, Object> operation, Map<String, Object> job) {
        Map<String, Object> result = operationResponse(status, alreadyExists, operation);
        result.put("safe_to_retry", safeToRetry);
        result.put("job", snapshot(job));
        return result;
    }

    private static Map<String, Object> evidenceResponse(String status, boolean alreadyExists, Map<String, Object> raw) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", status);
        result.put("already_exists", alreadyExists);
        Map<String, Object> evidence = new LinkedHashMap<>(raw);
        Object artifactRef = evidence.remove("artifact_ref_json");
        if (artifactRef instanceof String value) evidence.put("artifact_ref", parseJson(value));
        result.put("evidence", evidence);
        return result;
    }

    private static Map<String, Object> requiredBody(Map<String, Object> body) {
        if (body == null) throw new RequestValidationException("REQUEST_BODY_REQUIRED", "A JSON object body is required.");
        return body;
    }

    private static String requiredId(Map<String, Object> body, String key) {
        Object value = body.get(key);
        if (!(value instanceof String string) || string.isBlank()) throw new RequestValidationException("MISSING_" + key.toUpperCase(Locale.ROOT), "Required identity field is missing: " + key);
        return requiredIdValue(string, key);
    }

    private static String optionalId(Map<String, Object> body, String key, String fallback) {
        Object value = body.get(key);
        if (value == null) return fallback;
        if (!(value instanceof String string) || string.isBlank()) throw new RequestValidationException("INVALID_" + key.toUpperCase(Locale.ROOT), "Identity field must be a non-empty string: " + key);
        return requiredIdValue(string, key);
    }

    private static String requiredIdValue(String value, String key) {
        if (value == null || value.isBlank() || !value.matches("[A-Za-z0-9._:-]{1,512}")) throw new RequestValidationException("INVALID_" + key.toUpperCase(Locale.ROOT), "Identity field contains unsupported characters: " + key);
        return value;
    }

    private static String requiredState(String value) {
        String state = value.trim().toUpperCase(Locale.ROOT);
        if (!Set.of("QUEUED", "CLAIMED", "RUNNING", "CANCEL_REQUESTED", "RECONCILE_REQUIRED", "COMPLETED", "FAILED_PLATFORM", "CANCELLED").contains(state)) throw new RequestValidationException("INVALID_STATE", "Unknown durable execution state.");
        return state;
    }

    private static String text(Map<String, Object> row, String key) {
        Object value = row == null ? null : row.get(key);
        return value == null ? null : String.valueOf(value);
    }

    private static String optionalText(Object value) {
        return value instanceof String string && !string.isBlank() ? requiredIdValue(string, "receipt_ref") : null;
    }

    private static int integer(Map<String, Object> body, String key, int min, int max, int fallback) {
        Object value = body.get(key);
        if (value == null) return fallback;
        int parsed = integerValue(value);
        if (parsed < min || parsed > max) throw new RequestValidationException("INVALID_" + key.toUpperCase(Locale.ROOT), key + " must be between " + min + " and " + max + ".");
        return parsed;
    }

    private static int integerValue(Object value) {
        if (value instanceof Number number) return number.intValue();
        try { return Integer.parseInt(String.valueOf(value)); }
        catch (NumberFormatException exception) { throw new RequestValidationException("INVALID_INTEGER", "Expected an integer field."); }
    }

    private static long requiredLong(Map<String, Object> body, String key) {
        Object value = body.get(key);
        if (value == null) throw new RequestValidationException("MISSING_" + key.toUpperCase(Locale.ROOT), "Required fencing field is missing: " + key);
        try { return value instanceof Number number ? number.longValue() : Long.parseLong(String.valueOf(value)); }
        catch (NumberFormatException exception) { throw new RequestValidationException("INVALID_" + key.toUpperCase(Locale.ROOT), "Fencing field must be an integer: " + key); }
    }

    private static long version(Map<String, Object> row) {
        return ((Number) row.get("version")).longValue();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> payloadRef(Object value) {
        if (value == null) return new LinkedHashMap<>();
        if (!(value instanceof Map<?, ?> map)) throw new RequestValidationException("INVALID_PAYLOAD_REF", "payload_ref must be a JSON object containing metadata references only.");
        ensureSafe(value);
        Map<String, Object> result = new LinkedHashMap<>((Map<String, Object>) map);
        if (json(result).length() > 16_384) throw new RequestValidationException("PAYLOAD_REF_TOO_LARGE", "Execution payload references must remain bounded.");
        return result;
    }

    @SuppressWarnings("unchecked")
    private String safeDiagnosticContext(Object value) {
        if (value == null) return null;
        if (!(value instanceof Map<?, ?> raw)) {
            throw new RequestValidationException("INVALID_OBSERVABILITY_CONTEXT", "Observability context must be a bounded object.");
        }
        Map<String, Object> input = new LinkedHashMap<>((Map<String, Object>) raw);
        if (!Objects.equals(input.get("schema_version"), ObservabilityService.CONTEXT_SCHEMA)) {
            throw new RequestValidationException("INVALID_OBSERVABILITY_CONTEXT", "Unsupported observability context schema.");
        }
        Object traceparent = input.get("traceparent");
        if (!(traceparent instanceof String valueText) || !valueText.matches("00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}")) {
            throw new RequestValidationException("INVALID_OBSERVABILITY_CONTEXT", "Observability context traceparent is malformed.");
        }
        Object baggage = input.get("baggage");
        Map<String, Object> safeBaggage = new LinkedHashMap<>();
        if (baggage != null) {
            if (!(baggage instanceof Map<?, ?> baggageMap)) {
                throw new RequestValidationException("INVALID_OBSERVABILITY_CONTEXT", "Observability baggage must be an object.");
            }
            for (Map.Entry<?, ?> entry : baggageMap.entrySet()) {
                String key = String.valueOf(entry.getKey());
                if (!ObservabilityService.BAGGAGE_ALLOWLIST.contains(key)
                        || !(entry.getValue() instanceof String safeValue)
                        || !safeValue.matches("[A-Za-z0-9._:-]{1,200}")) {
                    throw new RequestValidationException("INVALID_OBSERVABILITY_CONTEXT", "Observability baggage contains a forbidden or malformed field.");
                }
                safeBaggage.put(key, safeValue);
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("schema_version", ObservabilityService.CONTEXT_SCHEMA);
        result.put("traceparent", valueText);
        result.put("baggage", safeBaggage);
        if (json(result).length() > 2_048) {
            throw new RequestValidationException("INVALID_OBSERVABILITY_CONTEXT", "Observability context is too large.");
        }
        return json(result);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value, String key) {
        if (!(value instanceof Map<?, ?> map)) throw new RequestValidationException("INVALID_" + key.toUpperCase(Locale.ROOT), key + " must be a JSON object.");
        return new LinkedHashMap<>((Map<String, Object>) map);
    }

    private static void ensureSafe(Object value) {
        if (value instanceof Map<?, ?> map) {
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                String key = String.valueOf(entry.getKey()).toLowerCase(Locale.ROOT);
                for (String forbidden : FORBIDDEN_KEYS) if (key.contains(forbidden)) throw new RequestValidationException("FORBIDDEN_PAYLOAD_FIELD", "Job/evidence payload cannot contain secret or private protocol fields.");
                ensureSafe(entry.getValue());
            }
        } else if (value instanceof Iterable<?> iterable) {
            for (Object item : iterable) ensureSafe(item);
        } else if (value instanceof String string) {
            String lowered = string.toLowerCase(Locale.ROOT);
            if (lowered.contains("bearer ") || lowered.contains("private reasoning") || lowered.contains("chain_of_thought")) throw new RequestValidationException("FORBIDDEN_PAYLOAD_VALUE", "Job/evidence payload cannot contain credentials or private protocol text.");
        }
    }

    private static void ensureSameSubmission(Map<String, Object> existing, String fingerprint, String jobType, String targetType, String targetId) {
        if (!Objects.equals(existing.get("request_fingerprint"), fingerprint)
                || !Objects.equals(existing.get("job_type"), jobType)
                || !Objects.equals(existing.get("target_type"), targetType)
                || !Objects.equals(existing.get("target_id"), targetId)) throw new IdentityConflictException("IDEMPOTENCY_CONFLICT", "The idempotency key or job identity is already bound to different content.");
    }

    private String json(Object value) {
        try { return mapper.writeValueAsString(value); }
        catch (JsonProcessingException exception) { throw new RequestValidationException("INVALID_JSON_PAYLOAD", "Metadata payload could not be serialized."); }
    }

    private static Object parseJson(String value) {
        if (value == null) return null;
        try { return new ObjectMapper().readValue(value, Object.class); }
        catch (JsonProcessingException exception) { return Map.of("parse_error", true); }
    }

    private int count(String sql, Object... args) {
        Integer result = jdbc.queryForObject(sql, Integer.class, args);
        return result == null ? 0 : result;
    }

    private void mark(HttpServletRequest request, String entityType, String entityId) {
        request.setAttribute("rpf.control-plane.entity-type", entityType);
        request.setAttribute("rpf.control-plane.entity-id", entityId);
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder();
            for (byte item : digest) result.append(String.format("%02x", item));
            return result.toString();
        } catch (Exception exception) { throw new IllegalStateException("SHA-256 is unavailable", exception); }
    }

}
