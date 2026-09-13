package com.runproof.rpf10;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

import static com.runproof.rpf10.ProbeExceptions.RequestValidationException;

/** Small authenticated HTTP/JSON boundary used only by the RPF-10 probe. */
@RestController
@RequestMapping("/api/v1")
public class ControlPlaneController {

    private final PersistenceSchema persistenceSchema;
    private final CanonicalMetadataService metadataService;
    private final AuthService authService;
    private final AuditService auditService;
    private final ConfigurableApplicationContext applicationContext;

    public ControlPlaneController(
            PersistenceSchema persistenceSchema,
            CanonicalMetadataService metadataService,
            AuthService authService,
            AuditService auditService,
            ConfigurableApplicationContext applicationContext
    ) {
        this.persistenceSchema = persistenceSchema;
        this.metadataService = metadataService;
        this.authService = authService;
        this.auditService = auditService;
        this.applicationContext = applicationContext;
    }

    /** Liveness/readiness is public; all data and mutation APIs are protected. */
    @GetMapping("/health")
    public ResponseEntity<ApiModels.HealthResponse> health() {
        boolean databaseReady = persistenceSchema.isReady() && persistenceSchema.databaseResponding();
        PersistenceSchema.DatabaseIdentity identity = persistenceSchema.databaseIdentity();
        ApiModels.HealthResponse response = new ApiModels.HealthResponse(
                databaseReady ? "UP" : "DOWN",
                databaseReady ? "READY" : "NOT_READY",
                databaseReady ? "RESPONDING" : "UNAVAILABLE",
                PersistenceSchema.SCHEMA_VERSION,
                identity.product(),
                identity.version(),
                identity.jdbcDriver(),
                identity.jdbcDriverVersion(),
                identity.databaseName(),
                identity.schema()
        );
        return ResponseEntity.status(databaseReady ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE).body(response);
    }

    @PostMapping("/ingest/completed-evidence")
    public ResponseEntity<ApiModels.IngestResponse> ingest(
            HttpServletRequest request,
            @RequestBody ApiModels.IngestManifest manifest,
            @RequestParam(name = "fail_after_write", defaultValue = "false") boolean failAfterWrite
    ) {
        mark(request, "INGEST_COMPLETED_EVIDENCE", manifest == null ? null : manifest.entityId());
        String entityType = manifest == null ? "" : manifest.entityType();
        String requiredScope = "RELEASE_DECISION".equalsIgnoreCase(entityType)
                ? "decision:write"
                : "evidence:write";
        authService.require(request, requiredScope);
        ApiModels.IngestResponse response = metadataService.ingest(manifest, failAfterWrite);
        return ResponseEntity.status(response.alreadyExists() ? HttpStatus.OK : HttpStatus.CREATED).body(response);
    }

    /** Dedicated registration path used to test the decision-writer boundary. */
    @PostMapping("/release-decisions")
    public ResponseEntity<ApiModels.IngestResponse> registerDecision(
            HttpServletRequest request,
            @RequestBody ApiModels.IngestManifest manifest,
            @RequestParam(name = "fail_after_write", defaultValue = "false") boolean failAfterWrite
    ) {
        mark(request, "REGISTER_RELEASE_DECISION", manifest == null ? null : manifest.entityId());
        authService.require(request, "decision:write");
        if (manifest == null || !"RELEASE_DECISION".equalsIgnoreCase(manifest.entityType())) {
            throw new RequestValidationException("INVALID_DECISION_MANIFEST", "Only Release Decision manifests may use this endpoint.");
        }
        ApiModels.IngestResponse response = metadataService.ingest(manifest, failAfterWrite);
        return ResponseEntity.status(response.alreadyExists() ? HttpStatus.OK : HttpStatus.CREATED).body(response);
    }

    @GetMapping("/metadata/{entityType}/{entityId}")
    public ApiModels.MetadataView metadata(
            HttpServletRequest request,
            @PathVariable String entityType,
            @PathVariable String entityId
    ) {
        authService.require(request, "metadata:read");
        return metadataService.get(entityType, entityId);
    }

    @GetMapping("/runs/{entityId}")
    public ApiModels.MetadataView run(HttpServletRequest request, @PathVariable String entityId) {
        authService.require(request, "metadata:read");
        return metadataService.get("RUN", entityId);
    }

    @GetMapping("/evaluations/{entityId}")
    public ApiModels.MetadataView evaluation(HttpServletRequest request, @PathVariable String entityId) {
        authService.require(request, "metadata:read");
        return metadataService.get("EVALUATION", entityId);
    }

    @GetMapping("/release-decisions/{entityId}")
    public ApiModels.MetadataView releaseDecision(HttpServletRequest request, @PathVariable String entityId) {
        authService.require(request, "metadata:read");
        return metadataService.get("RELEASE_DECISION", entityId);
    }

    @GetMapping("/release-decisions")
    public ApiModels.MetadataList releaseDecisions(HttpServletRequest request) {
        authService.require(request, "metadata:read");
        return metadataService.list("RELEASE_DECISION");
    }

    @GetMapping("/probe/audit")
    public ApiModels.AuditList audit(HttpServletRequest request) {
        authService.require(request, "metadata:read");
        return auditService.list();
    }

    @GetMapping("/probe/boundary")
    public Map<String, Object> boundary(HttpServletRequest request) {
        authService.require(request, "metadata:read");
        return Map.of(
                "authentication", "SERVICE_BEARER_ENV",
                "runtime_evidence_scope", "evidence:write",
                "decision_authority_scope", "decision:write",
                "read_scope", "metadata:read",
                "agent_has_release_decision_authority", false,
                "approval_authority_implemented", false,
                "release_or_deploy_authorized", false,
                "transport", "SYNCHRONOUS_HTTP_JSON",
                "job_transport_resolved", false,
                "queue_or_broker", false,
                "ci_integration", "FUTURE_CONTRACT_ONLY",
                "active_scopes", List.of("metadata:read", "evidence:write", "decision:write", "agent:observe")
        );
    }

    /** Probe-only graceful shutdown so the Python probe can close the JVM. */
    @PostMapping("/probe/shutdown")
    public Map<String, String> shutdown(HttpServletRequest request) {
        authService.require(request, "metadata:read");
        Thread shutdown = new Thread(() -> {
            try {
                Thread.sleep(100);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
            int exitCode = SpringApplication.exit(applicationContext);
            System.exit(exitCode);
        }, "rpf10-probe-shutdown");
        shutdown.setDaemon(true);
        shutdown.start();
        return Map.of("status", "SHUTTING_DOWN");
    }

    private static void mark(HttpServletRequest request, String action, String entityId) {
        request.setAttribute("rpf10.audit.action", action);
        if (entityId != null && !entityId.isBlank()) {
            request.setAttribute("rpf10.audit.entity", entityId);
        }
    }
}
