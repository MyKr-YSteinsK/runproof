package com.runproof.rpf13;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
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

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

import static com.runproof.rpf13.ProbeExceptions.ApiException;
import static com.runproof.rpf13.ProbeExceptions.badRequest;
import static com.runproof.rpf13.ProbeExceptions.conflict;
import static com.runproof.rpf13.ProbeExceptions.notFound;
import static com.runproof.rpf13.ProbeExceptions.reconcileRequired;

/**
 * Small real PostgreSQL durable execution candidate used only by RPF-13.
 *
 * <p>The mutable job row is the coordination record. Attempts, operations,
 * simulated effects and evidence are separate tables. All owner-sensitive
 * mutations use the current attempt id, worker id, lease token and fenced
 * lease version; the token is only returned at claim time and only its hash
 * is stored.</p>
 */
@RestController
@RequestMapping("/api/v1")
public class DurableExecutionController {

    private static final Set<String> TERMINAL_STATES = Set.of("COMPLETED", "FAILED_PLATFORM", "CANCELLED");
    private static final Set<String> OWNER_STATES = Set.of("CLAIMED", "RUNNING", "CANCEL_REQUESTED");
    private static final Set<String> UNSAFE_OPERATION_STATES = Set.of("PREPARED", "IN_FLIGHT", "UNKNOWN_OUTCOME");
    private static final Set<String> EVIDENCE_OUTCOMES = Set.of("PASS", "FAIL", "ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED");
    private static final Set<String> FORBIDDEN_KEYS = Set.of(
            "authorization", "token", "secret", "password", "credential", "api_key", "apikey",
            "prompt", "message", "messages", "reasoning", "chain_of_thought", "private_thought"
    );

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final PersistenceSchema schema;
    private final TransactionTemplate transactions;

    public DurableExecutionController(
            JdbcTemplate jdbc,
            ObjectMapper mapper,
            PersistenceSchema schema,
            PlatformTransactionManager transactionManager
    ) {
        this.jdbc = jdbc;
        this.mapper = mapper;
        this.schema = schema;
        this.transactions = new TransactionTemplate(transactionManager);
    }

    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> health() {
        boolean database = schema.databaseResponding();
        boolean ready = schema.isReady() && database;
        PersistenceSchema.DatabaseIdentity identity = schema.databaseIdentity();
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", "ALIVE");
        body.put("readiness", ready ? "READY" : "NOT_READY");
        body.put("ready", ready);
        body.put("database", database ? "REACHABLE" : "UNAVAILABLE");
        body.put("schema_version", PersistenceSchema.SCHEMA_VERSION);
        body.put("database_product", identity.product());
        body.put("database_version", identity.version());
        body.put("jdbc_driver", identity.jdbcDriver());
        body.put("database_name", identity.databaseName());
        return ResponseEntity.status(ready ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE).body(body);
    }

    @GetMapping("/capabilities")
    public Map<String, Object> capabilities() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("schema_version", PersistenceSchema.SCHEMA_VERSION);
        body.put("execution_state_store", "POSTGRESQL");
        body.put("transport_candidate", "POSTGRESQL_POLL_CLAIM_LEASE");
        body.put("delivery_semantics", "AT_LEAST_ONCE");
        body.put("side_effect_rule", "OPERATION_ID_PLUS_RECONCILE");
        body.put("evidence_boundary", "SEPARATE_APPEND_ONLY_TABLE");
        body.put("release_authority", false);
        body.put("approval_authority", false);
        body.put("scheduler", false);
        body.put("broker", false);
        body.put("production_worker", false);
        body.put("supported_states", List.of(
                "QUEUED", "CLAIMED", "RUNNING", "CANCEL_REQUESTED", "RECONCILE_REQUIRED",
                "COMPLETED", "FAILED_PLATFORM", "CANCELLED"
        ));
        return body;
    }

    @PostMapping("/jobs")
    public ResponseEntity<Map<String, Object>> submit(@RequestBody Map<String, Object> rawBody) {
        Map<String, Object> body = requiredBody(rawBody);
        String jobId = optionalId(body, "job_id", "job-" + UUID.randomUUID());
        String idempotencyKey = requiredId(body, "idempotency_key");
        String fingerprint = requiredId(body, "request_fingerprint");
        String jobType = requiredId(body, "job_type");
        String targetType = requiredId(body, "target_type");
        String targetId = requiredId(body, "target_id");
        String correlationId = optionalId(body, "correlation_id", "rpf13-" + UUID.randomUUID());
        Map<String, Object> payloadRef = payloadRef(body.get("payload_ref"));
        return ResponseEntity.status(HttpStatus.OK).body(transactions.execute(status -> {
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
                        cancel_requested, timeout_requested, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', 0, 0, FALSE, FALSE, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    jobId, idempotencyKey, fingerprint, jobType, targetType, targetId,
                    json(payloadRef), correlationId, Timestamp.from(now), Timestamp.from(now)
            );
            if (inserted == 0) {
                Map<String, Object> winner = findJobByIdempotency(idempotencyKey, true);
                if (winner == null) {
                    winner = findJob(jobId, true, false);
                }
                if (winner == null) {
                    throw conflict("SUBMIT_RACE_UNRESOLVED", "Concurrent job submission did not produce a readable winner.");
                }
                ensureSameSubmission(winner, fingerprint, jobType, targetType, targetId);
                return response("IDEMPOTENT_REPLAY", true, winner.get("job_id"), snapshot(winner));
            }
            insertEvent(jobId, null, "QUEUED", "JOB_SUBMITTED", null, null, 0L, "DURABLE_SUBMIT", now);
            Map<String, Object> created = findJob(jobId, false, true);
            return response("SUBMITTED", false, jobId, snapshot(created));
        }));
    }

    @GetMapping("/jobs/{jobId}")
    public Map<String, Object> getJob(@PathVariable String jobId) {
        return snapshot(findJob(requiredIdValue(jobId, "job_id"), false, true));
    }

    @PostMapping("/jobs/{jobId}/claim")
    public ResponseEntity<Map<String, Object>> claim(
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String workerId = requiredId(body, "worker_id");
        int leaseSeconds = integer(body, "lease_seconds", 1, 30, 5);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        Map<String, Object> result = transactions.execute(status -> claimLocked(normalizedJobId, workerId, leaseSeconds));
        return ResponseEntity.ok(result);
    }

    @PostMapping("/jobs/{jobId}/start")
    public Map<String, Object> start(
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            if ("RUNNING".equals(job.get("state"))) {
                requireOwner(job, body);
                return response("ALREADY_RUNNING", true, normalizedJobId, snapshot(job));
            }
            requireOwner(job, body);
            if (!"CLAIMED".equals(job.get("state"))) {
                throw conflict("JOB_NOT_STARTABLE", "Only a claimed attempt can enter RUNNING.");
            }
            long version = version(job) + 1;
            jdbc.update("UPDATE rpf_execution_job SET state='RUNNING', version=?, updated_at=? WHERE job_id=?", version, Timestamp.from(Instant.now()), normalizedJobId);
            jdbc.update("UPDATE rpf_execution_attempt SET status='RUNNING', lease_version=?, started_at=COALESCE(started_at, ?) WHERE attempt_id=?", version, Timestamp.from(Instant.now()), job.get("active_attempt_id"));
            insertEvent(normalizedJobId, "CLAIMED", "RUNNING", "ATTEMPT_STARTED", text(job, "active_attempt_id"), null, version, "WORKER_STARTED", Instant.now());
            Map<String, Object> updated = findJob(normalizedJobId, false, true);
            return response("RUNNING", false, normalizedJobId, snapshot(updated));
        });
    }

    @PostMapping("/jobs/{jobId}/heartbeat")
    public Map<String, Object> heartbeat(
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        int leaseSeconds = integer(body, "lease_seconds", 1, 30, 5);
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Instant now = Instant.now();
            Instant expires = now.plusSeconds(leaseSeconds);
            long version = version(job) + 1;
            jdbc.update("""
                    UPDATE rpf_execution_job
                    SET version=?, lease_expires_at=?, heartbeat_at=?, updated_at=?
                    WHERE job_id=?
                    """, version, Timestamp.from(expires), Timestamp.from(now), Timestamp.from(now), normalizedJobId);
            jdbc.update("""
                    UPDATE rpf_execution_attempt
                    SET lease_version=?, lease_expires_at=?, heartbeat_at=?
                    WHERE attempt_id=?
                    """, version, Timestamp.from(expires), Timestamp.from(now), job.get("active_attempt_id"));
            insertEvent(normalizedJobId, text(job, "state"), text(job, "state"), "LEASE_HEARTBEAT", text(job, "active_attempt_id"), null, version, "LEASE_EXTENDED", now);
            Map<String, Object> updated = findJob(normalizedJobId, false, true);
            Map<String, Object> result = response("HEARTBEAT_ACCEPTED", false, normalizedJobId, snapshot(updated));
            result.put("lease", leaseDetails(updated, text(job, "active_lease_token_hash"), body.get("lease_token"), version, expires));
            return result;
        });
    }

    @PostMapping("/jobs/{jobId}/operations")
    public Map<String, Object> prepareOperation(
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String operationId = requiredId(body, "operation_id");
        String environmentId = requiredId(body, "environment_id");
        String operationFingerprint = requiredId(body, "operation_fingerprint");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> existing = findOperation(operationId, true);
            if (existing != null) {
                if (!Objects.equals(existing.get("job_id"), normalizedJobId) || !Objects.equals(existing.get("operation_fingerprint"), operationFingerprint)) {
                    throw conflict("OPERATION_IDENTITY_CONFLICT", "operation_id is already bound to a different operation.");
                }
                return operationResponse("IDEMPOTENT_REPLAY", true, existing);
            }
            Instant now = Instant.now();
            jdbc.update("""
                    INSERT INTO rpf_execution_operation(
                        operation_id, job_id, attempt_id, environment_id, operation_fingerprint,
                        status, effect_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'PREPARED', 0, ?, ?)
                    """, operationId, normalizedJobId, job.get("active_attempt_id"), environmentId,
                    operationFingerprint, Timestamp.from(now), Timestamp.from(now));
            Map<String, Object> created = findOperation(operationId, false);
            return operationResponse("PREPARED", false, created);
        });
    }

    @PostMapping("/jobs/{jobId}/operations/{operationId}/not-submitted")
    public Map<String, Object> markNotSubmitted(
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("NOT_SUBMITTED".equals(current)) {
                return operationResponse("NOT_SUBMITTED", true, operation);
            }
            if (!"PREPARED".equals(current)) {
                throw reconcileRequired("Only a prepared operation with durable proof of non-submission can be marked NOT_SUBMITTED.");
            }
            jdbc.update("UPDATE rpf_execution_operation SET status='NOT_SUBMITTED', updated_at=? WHERE operation_id=?", Timestamp.from(Instant.now()), normalizedOperationId);
            return operationResponse("NOT_SUBMITTED", false, findOperation(normalizedOperationId, false));
        });
    }

    @PostMapping("/jobs/{jobId}/operations/{operationId}/apply")
    public ResponseEntity<Map<String, Object>> apply(
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody,
            @RequestParam(name = "simulate_response_lost", defaultValue = "false") boolean simulateResponseLost
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        Map<String, Object> result = transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("UNKNOWN_OUTCOME".equals(current) || "IN_FLIGHT".equals(current)) {
                throw reconcileRequired("The operation may have been submitted; reconcile before mutation retry.");
            }
            if ("CONFIRMED".equals(current)) {
                return operationResponse("IDEMPOTENT_REPLAY", true, operation);
            }
            if (!Set.of("PREPARED", "NOT_SUBMITTED").contains(current)) {
                throw conflict("OPERATION_NOT_APPLYABLE", "The operation is not in a safe-to-submit state.");
            }
            Instant now = Instant.now();
            String receipt = "receipt-" + normalizedOperationId;
            jdbc.update("""
                    INSERT INTO rpf_simulated_effect(operation_id, job_id, environment_id, receipt_ref, applied_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (operation_id) DO NOTHING
                    """, normalizedOperationId, normalizedJobId, operation.get("environment_id"), receipt, Timestamp.from(now));
            int effectCount = jdbc.queryForObject("SELECT COUNT(*) FROM rpf_simulated_effect WHERE operation_id=?", Integer.class, normalizedOperationId);
            jdbc.update("UPDATE rpf_execution_operation SET status='IN_FLIGHT', effect_count=?, updated_at=? WHERE operation_id=?", effectCount, Timestamp.from(now), normalizedOperationId);
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
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("CONFIRMED".equals(current)) {
                return operationResponse("IDEMPOTENT_REPLAY", true, operation);
            }
            if (!"IN_FLIGHT".equals(current) || !effectExists(normalizedOperationId)) {
                throw reconcileRequired("No receipt/effect proof is available to confirm this operation.");
            }
            jdbc.update("UPDATE rpf_execution_operation SET status='CONFIRMED', receipt_ref=(SELECT receipt_ref FROM rpf_simulated_effect WHERE operation_id=?), updated_at=? WHERE operation_id=?", normalizedOperationId, Timestamp.from(Instant.now()), normalizedOperationId);
            return operationResponse("CONFIRMED", false, findOperation(normalizedOperationId, false));
        });
    }

    @PostMapping("/jobs/{jobId}/operations/{operationId}/unknown")
    public Map<String, Object> markUnknownOutcome(
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        requiredId(body, "worker_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("CONFIRMED".equals(current) || "NOT_SUBMITTED".equals(current)) {
                return operationResponse("ALREADY_RESOLVED", true, operation);
            }
            if (!Set.of("PREPARED", "IN_FLIGHT").contains(current)) {
                throw conflict("OPERATION_NOT_UNKNOWNABLE", "This operation cannot enter UNKNOWN_OUTCOME from its current state.");
            }
            jdbc.update("UPDATE rpf_execution_operation SET status='UNKNOWN_OUTCOME', updated_at=? WHERE operation_id=?", Timestamp.from(Instant.now()), normalizedOperationId);
            String attemptId = text(job, "active_attempt_id");
            long nextVersion = version(job) + 1;
            if (attemptId != null) {
                jdbc.update("UPDATE rpf_execution_attempt SET status='RECONCILE_REQUIRED', ended_at=?, reason=? WHERE attempt_id=?", Timestamp.from(Instant.now()), "UNKNOWN_OUTCOME", attemptId);
            }
            updateStateClear(job, "RECONCILE_REQUIRED", nextVersion, "UNKNOWN_OUTCOME", null, null, normalizedOperationId);
            insertEvent(normalizedJobId, text(job, "state"), "RECONCILE_REQUIRED", "UNKNOWN_OUTCOME", attemptId, normalizedOperationId, nextVersion, "RECONCILE_BEFORE_RETRY", Instant.now());
            return operationResponse("UNKNOWN_OUTCOME", false, findOperation(normalizedOperationId, false));
        });
    }

    @PostMapping("/jobs/{jobId}/operations/{operationId}/reconcile")
    public Map<String, Object> reconcile(
            @PathVariable String jobId,
            @PathVariable String operationId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        requiredId(body, "worker_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, true);
            String current = text(operation, "status");
            if ("CONFIRMED".equals(current)) {
                return reconcileResponse("CONFIRMED", false, false, operation, job);
            }
            if ("NOT_SUBMITTED".equals(current)) {
                return reconcileResponse("NOT_SUBMITTED", true, false, operation, job);
            }
            if (!Set.of("UNKNOWN_OUTCOME", "IN_FLIGHT", "PREPARED").contains(current)) {
                throw conflict("OPERATION_NOT_RECONCILABLE", "The operation has no unresolved outcome to reconcile.");
            }
            boolean effect = effectExists(normalizedOperationId);
            String nextStatus = effect ? "CONFIRMED" : "NOT_SUBMITTED";
            String receipt = effect ? text(jdbc.queryForMap("SELECT receipt_ref FROM rpf_simulated_effect WHERE operation_id=?", normalizedOperationId), "receipt_ref") : null;
            jdbc.update("UPDATE rpf_execution_operation SET status=?, effect_count=?, receipt_ref=?, updated_at=? WHERE operation_id=?", nextStatus, effect ? 1 : 0, receipt, Timestamp.from(Instant.now()), normalizedOperationId);
            String attemptId = text(job, "active_attempt_id");
            if (attemptId != null) {
                jdbc.update("UPDATE rpf_execution_attempt SET status='RECONCILED', ended_at=?, reason=? WHERE attempt_id=?", Timestamp.from(Instant.now()), "RECONCILED_" + nextStatus, attemptId);
            }
            long nextVersion = version(job) + 1;
            updateStateClear(job, "QUEUED", nextVersion, "RECONCILED_" + nextStatus, null, null, normalizedOperationId);
            insertEvent(normalizedJobId, text(job, "state"), "QUEUED", "OPERATION_RECONCILED", attemptId, normalizedOperationId, nextVersion, nextStatus, Instant.now());
            return reconcileResponse(nextStatus, "NOT_SUBMITTED".equals(nextStatus), false, findOperation(normalizedOperationId, false), findJob(normalizedJobId, false, true));
        });
    }

    @GetMapping("/jobs/{jobId}/operations/{operationId}")
    public Map<String, Object> getOperation(@PathVariable String jobId, @PathVariable String operationId) {
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String normalizedOperationId = requiredIdValue(operationId, "operation_id");
        Map<String, Object> operation = ownedOperation(normalizedJobId, normalizedOperationId, false);
        return operationResponse("READ", false, operation);
    }

    @PostMapping("/jobs/{jobId}/evidence")
    public Map<String, Object> ingestEvidence(
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String evidenceId = requiredId(body, "evidence_id");
        String entityType = requiredId(body, "entity_type");
        String entityId = requiredId(body, "entity_id");
        String outcome = requiredId(body, "outcome").toUpperCase(Locale.ROOT);
        if (!EVIDENCE_OUTCOMES.contains(outcome)) {
            throw badRequest("INVALID_EVIDENCE_OUTCOME", "Evidence outcome is outside the existing RunProof outcome contract.");
        }
        String contentSha = requiredId(body, "content_sha256");
        Map<String, Object> artifactRef = object(body.get("artifact_ref"), "artifact_ref");
        ensureSafe(body);
        return transactions.execute(status -> {
            findJob(normalizedJobId, true, true);
            Map<String, Object> byId = findEvidence(evidenceId, true);
            Map<String, Object> byNaturalKey = findEvidenceByNaturalKey(normalizedJobId, entityType, entityId, true);
            Map<String, Object> existing = byId != null ? byId : byNaturalKey;
            if (existing != null) {
                if (!Objects.equals(existing.get("content_sha256"), contentSha)
                        || !Objects.equals(existing.get("entity_type"), entityType)
                        || !Objects.equals(existing.get("entity_id"), entityId)
                        || !Objects.equals(existing.get("job_id"), normalizedJobId)) {
                    throw conflict("IMMUTABLE_EVIDENCE_CONFLICT", "Evidence identity already exists with different immutable content.");
                }
                return evidenceResponse("IDEMPOTENT_REPLAY", true, existing);
            }
            Instant now = Instant.now();
            int inserted = jdbc.update("""
                    INSERT INTO rpf_execution_evidence(
                        evidence_id, job_id, entity_type, entity_id, outcome, content_sha256, artifact_ref_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """, evidenceId, normalizedJobId, entityType, entityId, outcome, contentSha, json(artifactRef), Timestamp.from(now));
            if (inserted == 0) {
                Map<String, Object> winner = findEvidence(evidenceId, true);
                if (winner == null) {
                    winner = findEvidenceByNaturalKey(normalizedJobId, entityType, entityId, true);
                }
                if (winner == null || !Objects.equals(winner.get("content_sha256"), contentSha)) {
                    throw conflict("IMMUTABLE_EVIDENCE_CONFLICT", "Concurrent evidence ingest produced a different immutable winner.");
                }
                return evidenceResponse("IDEMPOTENT_REPLAY", true, winner);
            }
            return evidenceResponse("EVIDENCE_STORED", false, findEvidence(evidenceId, false));
        });
    }

    @PostMapping("/jobs/{jobId}/complete")
    public Map<String, Object> complete(
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String evidenceId = requiredId(body, "evidence_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            if ("COMPLETED".equals(job.get("state")) && Objects.equals(job.get("terminal_evidence_id"), evidenceId)) {
                return response("IDEMPOTENT_REPLAY", true, normalizedJobId, snapshot(job));
            }
            requireOwner(job, body);
            if (!Set.of("CLAIMED", "RUNNING").contains(text(job, "state"))) {
                throw conflict("JOB_NOT_COMPLETABLE", "Only a claimed/running attempt can complete a job.");
            }
            Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
            if (hasUnsafeOperation(normalizedJobId)) {
                throw reconcileRequired("Completion is blocked until every prepared/in-flight/unknown operation is reconciled.");
            }
            finishTerminal(job, "COMPLETED", "COMPLETED", text(evidence, "outcome"), evidenceId, "EVIDENCE_COMMITTED", "ATTEMPT_COMPLETED");
            return response("COMPLETED", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
        });
    }

    @PostMapping("/jobs/{jobId}/fail-platform")
    public Map<String, Object> failPlatform(
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String evidenceId = requiredId(body, "evidence_id");
        String reason = requiredId(body, "reason");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
            if (!Set.of("ERROR", "INCONCLUSIVE").contains(text(evidence, "outcome"))) {
                throw badRequest("PLATFORM_FAILURE_EVIDENCE_REQUIRED", "Platform failure must use ERROR or INCONCLUSIVE evidence.");
            }
            finishTerminal(job, "FAILED_PLATFORM", "FAILED_PLATFORM", text(evidence, "outcome"), evidenceId, reason, "ATTEMPT_FAILED_PLATFORM");
            return response("FAILED_PLATFORM", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
        });
    }

    @PostMapping("/jobs/{jobId}/cancel")
    public Map<String, Object> cancel(
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            String state = text(job, "state");
            if (TERMINAL_STATES.contains(state)) {
                return response("TERMINAL", true, normalizedJobId, snapshot(job));
            }
            if ("QUEUED".equals(state)) {
                String evidenceId = requiredId(body, "evidence_id");
                Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
                if (!"CANCELLED".equals(text(evidence, "outcome"))) {
                    throw badRequest("CANCELLATION_EVIDENCE_REQUIRED", "Queued cancellation requires CANCELLED evidence.");
                }
                finishTerminal(job, "CANCELLED", "CANCELLED", "CANCELLED", evidenceId, "QUEUED_CANCELLED", "JOB_CANCELLED");
                return response("CANCELLED", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
            }
            if ("CANCEL_REQUESTED".equals(state)) {
                return response("CANCEL_REQUESTED", true, normalizedJobId, snapshot(job));
            }
            if (!OWNER_STATES.contains(state)) {
                throw conflict("JOB_NOT_CANCELLABLE", "The job is not at a cancellable execution boundary.");
            }
            long nextVersion = version(job) + 1;
            jdbc.update("UPDATE rpf_execution_job SET state='CANCEL_REQUESTED', cancel_requested=TRUE, version=?, updated_at=? WHERE job_id=?", nextVersion, Timestamp.from(Instant.now()), normalizedJobId);
            jdbc.update("UPDATE rpf_execution_attempt SET lease_version=? WHERE attempt_id=?", nextVersion, job.get("active_attempt_id"));
            insertEvent(normalizedJobId, state, "CANCEL_REQUESTED", "CANCELLATION_REQUESTED", text(job, "active_attempt_id"), null, nextVersion, "WAIT_FOR_WORKER_ACK", Instant.now());
            return response("CANCEL_REQUESTED", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
        });
    }

    @PostMapping("/jobs/{jobId}/cancel/ack")
    public Map<String, Object> acknowledgeCancel(
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String evidenceId = requiredId(body, "evidence_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            requireOwner(job, body);
            if (!"CANCEL_REQUESTED".equals(job.get("state"))) {
                throw conflict("CANCEL_NOT_REQUESTED", "Cancellation acknowledgement requires CANCEL_REQUESTED state.");
            }
            if (hasUnsafeOperation(normalizedJobId)) {
                throw reconcileRequired("Cancellation cannot finalize while a side effect has unresolved outcome.");
            }
            Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
            if (!"CANCELLED".equals(text(evidence, "outcome"))) {
                throw badRequest("CANCELLATION_EVIDENCE_REQUIRED", "Cancellation acknowledgement requires CANCELLED evidence.");
            }
            finishTerminal(job, "CANCELLED", "CANCELLED", "CANCELLED", evidenceId, "WORKER_ACKNOWLEDGED", "ATTEMPT_CANCELLED");
            return response("CANCELLED", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
        });
    }

    @PostMapping("/jobs/{jobId}/timeout")
    public Map<String, Object> timeout(
            @PathVariable String jobId,
            @RequestBody Map<String, Object> rawBody
    ) {
        Map<String, Object> body = requiredBody(rawBody);
        String normalizedJobId = requiredIdValue(jobId, "job_id");
        String evidenceId = requiredId(body, "evidence_id");
        return transactions.execute(status -> {
            Map<String, Object> job = findJob(normalizedJobId, true, true);
            String state = text(job, "state");
            if (TERMINAL_STATES.contains(state)) {
                return response("TERMINAL", true, normalizedJobId, snapshot(job));
            }
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
                    long nextVersion = version(job) + 1;
                    jdbc.update("UPDATE rpf_execution_attempt SET status='RECONCILE_REQUIRED', ended_at=?, reason=? WHERE attempt_id=?", Timestamp.from(Instant.now()), "TIMEOUT_RECONCILE_REQUIRED", attemptId);
                    updateStateClear(job, "RECONCILE_REQUIRED", nextVersion, "TIMEOUT_RECONCILE_REQUIRED", null, null, text(job, "last_operation_id"));
                    insertEvent(normalizedJobId, state, "RECONCILE_REQUIRED", "TIMEOUT_RECONCILE_REQUIRED", attemptId, text(job, "last_operation_id"), nextVersion, "NO_BLIND_AGENT_FAIL", Instant.now());
                    return response("RECONCILE_REQUIRED", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
                }
                Map<String, Object> evidence = evidenceForJob(normalizedJobId, evidenceId, true);
                requirePlatformOutcome(evidence);
                finishTerminal(job, "FAILED_PLATFORM", "FAILED_PLATFORM", text(evidence, "outcome"), evidenceId, "TIMEOUT_SAFE_BOUNDARY", "JOB_TIMEOUT_PLATFORM");
                return response("FAILED_PLATFORM", false, normalizedJobId, snapshot(findJob(normalizedJobId, false, true)));
            }
            throw conflict("JOB_NOT_TIMEOUTABLE", "The job is not at an executable timeout boundary.");
        });
    }

    private Map<String, Object> claimLocked(String jobId, String workerId, int leaseSeconds) {
        Map<String, Object> job = findJob(jobId, true, true);
        String state = text(job, "state");
        if (TERMINAL_STATES.contains(state)) {
            return response("TERMINAL", false, jobId, snapshot(job));
        }
        if ("RECONCILE_REQUIRED".equals(state)) {
            return response("RECONCILE_REQUIRED", false, jobId, snapshot(job));
        }
        if ("CANCEL_REQUESTED".equals(state)) {
            return response("CANCEL_REQUESTED", false, jobId, snapshot(job));
        }
        String activeAttempt = text(job, "active_attempt_id");
        if (activeAttempt != null) {
            boolean expired = Boolean.TRUE.equals(jdbc.queryForObject(
                    "SELECT lease_expires_at <= CURRENT_TIMESTAMP FROM rpf_execution_job WHERE job_id=?",
                    Boolean.class, jobId
            ));
            if (!expired) {
                throw conflict("ACTIVE_LEASE", "Another worker currently owns the job lease.");
            }
            if (hasUnsafeOperationForAttempt(activeAttempt)) {
                jdbc.update("UPDATE rpf_execution_attempt SET status='RECONCILE_REQUIRED', ended_at=?, reason=? WHERE attempt_id=?", Timestamp.from(Instant.now()), "LEASE_EXPIRED_RECONCILE_REQUIRED", activeAttempt);
                long nextVersion = version(job) + 1;
                updateStateClear(job, "RECONCILE_REQUIRED", nextVersion, "LEASE_EXPIRED_RECONCILE_REQUIRED", null, null, text(job, "last_operation_id"));
                insertEvent(jobId, state, "RECONCILE_REQUIRED", "LEASE_EXPIRED_REQUIRES_RECONCILE", activeAttempt, text(job, "last_operation_id"), nextVersion, "LEASE_EXPIRY_IS_NOT_PROOF_OF_NON_EXECUTION", Instant.now());
                return response("RECONCILE_REQUIRED", false, jobId, snapshot(findJob(jobId, false, true)));
            }
            jdbc.update("UPDATE rpf_execution_attempt SET status='EXPIRED', ended_at=?, reason=? WHERE attempt_id=?", Timestamp.from(Instant.now()), "LEASE_EXPIRED_SAFE_TO_RECLAIM", activeAttempt);
            long nextVersion = version(job) + 1;
            updateStateClear(job, "QUEUED", nextVersion, "LEASE_EXPIRED_SAFE_TO_RECLAIM", null, null, text(job, "last_operation_id"));
            insertEvent(jobId, state, "QUEUED", "LEASE_EXPIRED_REQUEUED", activeAttempt, null, nextVersion, "NO_UNCERTAIN_SIDE_EFFECT", Instant.now());
            job = findJob(jobId, true, true);
        }
        if (!"QUEUED".equals(job.get("state"))) {
            throw conflict("JOB_NOT_CLAIMABLE", "The job is not queued for a new attempt.");
        }
        Instant now = Instant.now();
        Instant expires = now.plusSeconds(leaseSeconds);
        String attemptId = "attempt-" + UUID.randomUUID();
        String leaseToken = UUID.randomUUID().toString() + UUID.randomUUID();
        long nextVersion = version(job) + 1;
        int attemptNumber = integerValue(job.get("attempt_number")) + 1;
        jdbc.update("""
                INSERT INTO rpf_execution_attempt(
                    attempt_id, job_id, attempt_number, worker_id, lease_token_hash, lease_version,
                    status, lease_expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'CLAIMED', ?, ?)
                """, attemptId, jobId, attemptNumber, workerId, sha256(leaseToken), nextVersion, Timestamp.from(expires), Timestamp.from(now));
        jdbc.update("""
                UPDATE rpf_execution_job
                SET state='CLAIMED', version=?, attempt_number=?, active_attempt_id=?, active_worker_id=?,
                    active_lease_token_hash=?, lease_expires_at=?, heartbeat_at=?, updated_at=?
                WHERE job_id=?
                """, nextVersion, attemptNumber, attemptId, workerId, sha256(leaseToken), Timestamp.from(expires), Timestamp.from(now), Timestamp.from(now), jobId);
        insertEvent(jobId, "QUEUED", "CLAIMED", "JOB_CLAIMED", attemptId, null, nextVersion, "POLL_CLAIM", now);
        Map<String, Object> updated = findJob(jobId, false, true);
        Map<String, Object> result = response("CLAIMED", false, jobId, snapshot(updated));
        result.put("lease", leaseDetails(updated, sha256(leaseToken), leaseToken, nextVersion, expires));
        return result;
    }

    private void finishTerminal(
            Map<String, Object> job,
            String state,
            String attemptStatus,
            String outcome,
            String evidenceId,
            String reason,
            String eventType
    ) {
        String jobId = text(job, "job_id");
        String attemptId = text(job, "active_attempt_id");
        long nextVersion = version(job) + 1;
        if (attemptId != null) {
            jdbc.update("UPDATE rpf_execution_attempt SET status=?, ended_at=?, reason=? WHERE attempt_id=?", attemptStatus, Timestamp.from(Instant.now()), reason, attemptId);
        }
        updateStateClear(job, state, nextVersion, reason, outcome, evidenceId, text(job, "last_operation_id"));
        insertEvent(jobId, text(job, "state"), state, eventType, attemptId, null, nextVersion, reason, Instant.now());
    }

    private void updateStateClear(
            Map<String, Object> oldJob,
            String state,
            long version,
            String reason,
            String outcome,
            String evidenceId,
            String operationId
    ) {
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
        if (!OWNER_STATES.contains(state)) {
            throw conflict("STALE_ATTEMPT", "The job no longer has an active owner attempt.");
        }
        String expectedAttempt = text(job, "active_attempt_id");
        String expectedWorker = text(job, "active_worker_id");
        String attempt = requiredId(body, "attempt_id");
        String worker = requiredId(body, "worker_id");
        String token = requiredId(body, "lease_token");
        long leaseVersion = requiredLong(body, "lease_version");
        if (!Objects.equals(expectedAttempt, attempt)
                || !Objects.equals(expectedWorker, worker)
                || leaseVersion != version(job)
                || !Objects.equals(text(job, "active_lease_token_hash"), sha256(token))) {
            throw conflict("STALE_ATTEMPT", "Attempt fencing rejected a stale or non-owner mutation.");
        }
    }

    private Map<String, Object> leaseDetails(Map<String, Object> job, String hash, Object token, long version, Instant expires) {
        Map<String, Object> lease = new LinkedHashMap<>();
        lease.put("attempt_id", job.get("active_attempt_id"));
        lease.put("worker_id", job.get("active_worker_id"));
        lease.put("lease_version", version);
        lease.put("lease_expires_at", expires == null ? job.get("lease_expires_at") : expires.toString());
        if (token instanceof String value && !value.isBlank()) {
            lease.put("lease_token", value);
        }
        lease.put("lease_token_present", hash != null);
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
        result.put("lease", leaseDetails(job, text(job, "active_lease_token_hash"), null, version(job), null));
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
                """, job.get("job_id"))) {
            attempts.add(new LinkedHashMap<>(attempt));
        }
        result.put("attempts", attempts);
        List<Map<String, Object>> operations = new ArrayList<>();
        for (Map<String, Object> operation : jdbc.queryForList("""
                SELECT operation_id, attempt_id, environment_id, status, effect_count, receipt_ref,
                       created_at::text AS created_at, updated_at::text AS updated_at
                FROM rpf_execution_operation WHERE job_id=? ORDER BY created_at, operation_id
                """, job.get("job_id"))) {
            operations.add(new LinkedHashMap<>(operation));
        }
        result.put("operations", operations);
        List<Map<String, Object>> evidence = new ArrayList<>();
        for (Map<String, Object> item : jdbc.queryForList("""
                SELECT evidence_id, entity_type, entity_id, outcome, content_sha256, artifact_ref_json,
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

    private Map<String, Object> selectJob(String jobId, boolean forUpdate) {
        return findJob(jobId, forUpdate, true);
    }

    private Map<String, Object> findJob(String jobId, boolean forUpdate, boolean throwIfMissing) {
        String sql = """
                SELECT job_id, idempotency_key, request_fingerprint, job_type, target_type, target_id,
                       payload_ref_json, correlation_id, state, version, attempt_number,
                       active_attempt_id, active_worker_id, active_lease_token_hash,
                       lease_expires_at::text AS lease_expires_at, heartbeat_at::text AS heartbeat_at,
                       cancel_requested, timeout_requested, outcome_status, platform_reason,
                       terminal_evidence_id, last_operation_id, created_at::text AS created_at,
                       updated_at::text AS updated_at
                FROM rpf_execution_job WHERE job_id=?
                """ + (forUpdate ? " FOR UPDATE" : "");
        try {
            return jdbc.queryForMap(sql, jobId);
        } catch (EmptyResultDataAccessException exception) {
            if (throwIfMissing) {
                throw notFound("Durable job does not exist: " + jobId);
            }
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
        if (operation == null || !Objects.equals(operation.get("job_id"), jobId)) {
            throw notFound("Durable operation does not exist for this job: " + operationId);
        }
        return operation;
    }

    private Map<String, Object> findEvidence(String evidenceId, boolean forUpdate) {
        String sql = """
                SELECT evidence_id, job_id, entity_type, entity_id, outcome, content_sha256, artifact_ref_json,
                       created_at::text AS created_at
                FROM rpf_execution_evidence WHERE evidence_id=?
                """ + (forUpdate ? " FOR UPDATE" : "");
        List<Map<String, Object>> rows = jdbc.queryForList(sql, evidenceId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private Map<String, Object> findEvidenceByNaturalKey(String jobId, String entityType, String entityId, boolean forUpdate) {
        String sql = """
                SELECT evidence_id, job_id, entity_type, entity_id, outcome, content_sha256, artifact_ref_json,
                       created_at::text AS created_at
                FROM rpf_execution_evidence WHERE job_id=? AND entity_type=? AND entity_id=?
                """ + (forUpdate ? " FOR UPDATE" : "");
        List<Map<String, Object>> rows = jdbc.queryForList(sql, jobId, entityType, entityId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private Map<String, Object> evidenceForJob(String jobId, String evidenceId, boolean forUpdate) {
        Map<String, Object> evidence = findEvidence(evidenceId, forUpdate);
        if (evidence == null || !Objects.equals(evidence.get("job_id"), jobId)) {
            throw notFound("Evidence does not exist for this durable job: " + evidenceId);
        }
        return evidence;
    }

    private boolean hasUnsafeOperation(String jobId) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM rpf_execution_operation WHERE job_id=? AND status IN ('PREPARED','IN_FLIGHT','UNKNOWN_OUTCOME')",
                Integer.class, jobId
        );
        return count != null && count > 0;
    }

    private boolean hasUnsafeOperationForAttempt(String attemptId) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM rpf_execution_operation WHERE attempt_id=? AND status IN ('PREPARED','IN_FLIGHT','UNKNOWN_OUTCOME')",
                Integer.class, attemptId
        );
        return count != null && count > 0;
    }

    private boolean effectExists(String operationId) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM rpf_simulated_effect WHERE operation_id=?", Integer.class, operationId);
        return count != null && count > 0;
    }

    private void requirePlatformOutcome(Map<String, Object> evidence) {
        if (!Set.of("ERROR", "INCONCLUSIVE").contains(text(evidence, "outcome"))) {
            throw badRequest("PLATFORM_FAILURE_EVIDENCE_REQUIRED", "Timeout/platform failure must use ERROR or INCONCLUSIVE evidence.");
        }
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
        if (artifactRef instanceof String value) {
            evidence.put("artifact_ref", parseJson(value));
        }
        result.put("evidence", evidence);
        return result;
    }

    private static Map<String, Object> requiredBody(Map<String, Object> body) {
        if (body == null) {
            throw badRequest("REQUEST_BODY_REQUIRED", "A JSON object body is required.");
        }
        return body;
    }

    private static String requiredId(Map<String, Object> body, String key) {
        Object value = body.get(key);
        if (!(value instanceof String string) || string.isBlank()) {
            throw badRequest("MISSING_" + key.toUpperCase(Locale.ROOT), "Required identity field is missing: " + key);
        }
        return requiredIdValue(string, key);
    }

    private static String optionalId(Map<String, Object> body, String key, String fallback) {
        Object value = body.get(key);
        if (value == null) {
            return fallback;
        }
        if (!(value instanceof String string) || string.isBlank()) {
            throw badRequest("INVALID_" + key.toUpperCase(Locale.ROOT), "Identity field must be a non-empty string: " + key);
        }
        return requiredIdValue(string, key);
    }

    private static String requiredIdValue(String value, String key) {
        if (value == null || value.isBlank() || !value.matches("[A-Za-z0-9._:-]{1,512}")) {
            throw badRequest("INVALID_" + key.toUpperCase(Locale.ROOT), "Identity field contains unsupported characters: " + key);
        }
        return value;
    }

    private static String text(Map<String, Object> row, String key) {
        Object value = row == null ? null : row.get(key);
        return value == null ? null : String.valueOf(value);
    }

    private static int integer(Map<String, Object> body, String key, int min, int max, int fallback) {
        Object value = body.get(key);
        if (value == null) {
            return fallback;
        }
        int parsed = integerValue(value);
        if (parsed < min || parsed > max) {
            throw badRequest("INVALID_" + key.toUpperCase(Locale.ROOT), key + " must be between " + min + " and " + max + ".");
        }
        return parsed;
    }

    private static int integerValue(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException exception) {
            throw badRequest("INVALID_INTEGER", "Expected an integer field.");
        }
    }

    private static long requiredLong(Map<String, Object> body, String key) {
        Object value = body.get(key);
        if (value == null) {
            throw badRequest("MISSING_" + key.toUpperCase(Locale.ROOT), "Required fencing field is missing: " + key);
        }
        try {
            return value instanceof Number number ? number.longValue() : Long.parseLong(String.valueOf(value));
        } catch (NumberFormatException exception) {
            throw badRequest("INVALID_" + key.toUpperCase(Locale.ROOT), "Fencing field must be an integer: " + key);
        }
    }

    private static long version(Map<String, Object> row) {
        return ((Number) row.get("version")).longValue();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> payloadRef(Object value) {
        if (value == null) {
            return new LinkedHashMap<>();
        }
        if (!(value instanceof Map<?, ?> map)) {
            throw badRequest("INVALID_PAYLOAD_REF", "payload_ref must be a JSON object containing metadata references only.");
        }
        ensureSafe(value);
        return new LinkedHashMap<>((Map<String, Object>) map);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value, String key) {
        if (!(value instanceof Map<?, ?> map)) {
            throw badRequest("INVALID_" + key.toUpperCase(Locale.ROOT), key + " must be a JSON object.");
        }
        return new LinkedHashMap<>((Map<String, Object>) map);
    }

    private static void ensureSafe(Object value) {
        if (value instanceof Map<?, ?> map) {
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                String key = String.valueOf(entry.getKey()).toLowerCase(Locale.ROOT);
                for (String forbidden : FORBIDDEN_KEYS) {
                    if (key.contains(forbidden)) {
                        throw badRequest("FORBIDDEN_PAYLOAD_FIELD", "Job/evidence payload cannot contain secret or private protocol fields.");
                    }
                }
                ensureSafe(entry.getValue());
            }
        } else if (value instanceof Iterable<?> iterable) {
            for (Object item : iterable) {
                ensureSafe(item);
            }
        }
    }

    private static void ensureSameSubmission(Map<String, Object> existing, String fingerprint, String jobType, String targetType, String targetId) {
        if (!Objects.equals(existing.get("request_fingerprint"), fingerprint)
                || !Objects.equals(existing.get("job_type"), jobType)
                || !Objects.equals(existing.get("target_type"), targetType)
                || !Objects.equals(existing.get("target_id"), targetId)) {
            throw conflict("IDEMPOTENCY_CONFLICT", "The idempotency key or job identity is already bound to different content.");
        }
    }

    private String json(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw badRequest("INVALID_JSON_PAYLOAD", "Metadata payload could not be serialized.");
        }
    }

    private static Object parseJson(String value) {
        if (value == null) {
            return null;
        }
        try {
            return new ObjectMapper().readValue(value, Object.class);
        } catch (JsonProcessingException exception) {
            return Map.of("parse_error", true);
        }
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder();
            for (byte item : digest) {
                result.append(String.format("%02x", item));
            }
            return result.toString();
        } catch (Exception exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }
}
