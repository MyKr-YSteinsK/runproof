package com.runproof.controlplane;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
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

@RestController
@RequestMapping("/api/v1")
public class ControlPlaneController {

    private final PersistenceSchema schema;
    private final LocalFileArtifactStore artifactStore;
    private final CanonicalMetadataService metadataService;
    private final AuditService auditService;
    private final AuthService authService;
    private final boolean probeEnabled;

    public ControlPlaneController(
            PersistenceSchema schema,
            LocalFileArtifactStore artifactStore,
            CanonicalMetadataService metadataService,
            AuditService auditService,
            AuthService authService,
            @Value("${rpf.probe.enabled:false}") boolean probeEnabled
    ) {
        this.schema = schema;
        this.artifactStore = artifactStore;
        this.metadataService = metadataService;
        this.auditService = auditService;
        this.authService = authService;
        this.probeEnabled = probeEnabled;
    }

    @GetMapping("/health")
    public ResponseEntity<ApiModels.HealthResponse> health() {
        boolean database = schema.databaseResponding();
        boolean store = artifactStore.isAvailable();
        boolean ready = schema.isMigrationValid() && database && store;
        PersistenceSchema.DatabaseIdentity identity = schema.databaseIdentity();
        ApiModels.HealthResponse response = new ApiModels.HealthResponse(
                "ALIVE",
                database ? "REACHABLE" : "UNAVAILABLE",
                schema.isMigrationValid() ? "VALID" : "INVALID",
                store ? "AVAILABLE" : "UNAVAILABLE",
                ready ? "READY" : "NOT_READY",
                ready,
                PersistenceSchema.SCHEMA_VERSION,
                identity.product(), identity.version(), identity.jdbcDriver(), identity.jdbcDriverVersion(),
                identity.databaseName(), identity.schema()
        );
        return ResponseEntity.status(ready ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE).body(response);
    }

    @GetMapping("/readyz")
    public ResponseEntity<Map<String, Object>> readyz() {
        boolean database = schema.databaseResponding();
        boolean store = artifactStore.isAvailable();
        boolean ready = schema.isMigrationValid() && database && store;
        Map<String, Object> body = Map.of(
                "ready", ready,
                "process", "ALIVE",
                "database", database ? "REACHABLE" : "UNAVAILABLE",
                "migration", schema.isMigrationValid() ? "VALID" : "INVALID",
                "artifact_store", store ? "AVAILABLE" : "UNAVAILABLE"
        );
        return ResponseEntity.status(ready ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE).body(body);
    }

    @GetMapping("/capabilities")
    public ApiModels.Boundary capabilities() {
        return new ApiModels.Boundary(
                "SYNCHRONOUS_HTTP_JSON",
                "POSTGRESQL_CANONICAL_METADATA",
                "IMMUTABLE_ARTIFACT_STORE_ABSTRACTION",
                "SERVICE_BEARER_ENV",
                List.of("metadata:read", "evidence:write", "decision:write", "agent:observe"),
                false, false, false, false, false, false, "FUTURE_CONTRACT_ONLY"
        );
    }

    @PostMapping("/ingest/completed-evidence")
    public ResponseEntity<ApiModels.IngestResponse> ingest(
            HttpServletRequest request,
            @RequestBody ApiModels.IngestManifest manifest,
            @RequestParam(name = "fail_after_write", defaultValue = "false") boolean failAfterWrite
    ) {
        mark(request, manifest);
        String entityType = manifest == null ? "" : normalize(manifest.entityType());
        if ("RELEASE_DECISION".equals(entityType)) {
            throw new ProbeExceptions.AuthorizationForbiddenException("decision:write");
        }
        Principal principal = authService.require(request, "evidence:write");
        if (failAfterWrite && !probeEnabled) {
            throw new ProbeExceptions.RequestValidationException("PROBE_MODE_REQUIRED", "Controlled rollback mode is disabled.");
        }
        ApiModels.IngestResponse response = metadataService.ingest(manifest, principal.id(), failAfterWrite);
        return ResponseEntity.status(response.alreadyExists() ? HttpStatus.OK : HttpStatus.CREATED).body(response);
    }

    @PostMapping("/release-decisions")
    public ResponseEntity<ApiModels.IngestResponse> registerDecision(
            HttpServletRequest request,
            @RequestBody ApiModels.IngestManifest manifest,
            @RequestParam(name = "fail_after_write", defaultValue = "false") boolean failAfterWrite
    ) {
        mark(request, manifest);
        Principal principal = authService.require(request, "decision:write");
        if (manifest == null || !"RELEASE_DECISION".equals(normalize(manifest.entityType()))) {
            throw new ProbeExceptions.RequestValidationException("INVALID_DECISION_MANIFEST", "Only Release Decision manifests may use this endpoint.");
        }
        if (failAfterWrite && !probeEnabled) {
            throw new ProbeExceptions.RequestValidationException("PROBE_MODE_REQUIRED", "Controlled rollback mode is disabled.");
        }
        ApiModels.IngestResponse response = metadataService.ingest(manifest, principal.id(), failAfterWrite);
        return ResponseEntity.status(response.alreadyExists() ? HttpStatus.OK : HttpStatus.CREATED).body(response);
    }

    @GetMapping("/metadata")
    public ApiModels.MetadataList metadataList(HttpServletRequest request, @RequestParam(name = "entity_type", required = false) String entityType) {
        authService.require(request, "metadata:read");
        return metadataService.list(entityType);
    }

    @GetMapping("/metadata/{entityType}/{entityId}")
    public ApiModels.MetadataView metadata(HttpServletRequest request, @PathVariable String entityType, @PathVariable String entityId) {
        authService.require(request, "metadata:read");
        mark(request, entityType, entityId);
        return metadataService.get(entityType, entityId);
    }

    @GetMapping("/runs")
    public ApiModels.MetadataList runs(HttpServletRequest request) {
        return list(request, "RUN");
    }

    @GetMapping("/runs/{entityId}")
    public ApiModels.MetadataView run(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "RUN", entityId);
    }

    @GetMapping("/failures")
    public ApiModels.MetadataList failures(HttpServletRequest request) {
        return list(request, "FAILURE_CASE");
    }

    @GetMapping("/failures/{entityId}")
    public ApiModels.MetadataView failure(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "FAILURE_CASE", entityId);
    }

    @GetMapping("/regressions")
    public ApiModels.MetadataList regressions(HttpServletRequest request) {
        return list(request, "REGRESSION");
    }

    @GetMapping("/regressions/{entityId}")
    public ApiModels.MetadataView regression(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "REGRESSION", entityId);
    }

    @GetMapping("/evaluations")
    public ApiModels.MetadataList evaluations(HttpServletRequest request) {
        return list(request, "EVALUATION");
    }

    @GetMapping("/evaluations/{entityId}")
    public ApiModels.MetadataView evaluation(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "EVALUATION", entityId);
    }

    @GetMapping("/comparisons")
    public ApiModels.MetadataList comparisons(HttpServletRequest request) {
        return list(request, "COMPARISON");
    }

    @GetMapping("/comparisons/{entityId}")
    public ApiModels.MetadataView comparison(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "COMPARISON", entityId);
    }

    @GetMapping("/release-decisions")
    public ApiModels.MetadataList releaseDecisions(HttpServletRequest request) {
        return list(request, "RELEASE_DECISION");
    }

    @GetMapping("/release-decisions/{entityId}")
    public ApiModels.MetadataView releaseDecision(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "RELEASE_DECISION", entityId);
    }

    @GetMapping("/artifacts/{entityType}/{entityId}")
    public ApiModels.ArtifactResponse artifact(HttpServletRequest request, @PathVariable String entityType, @PathVariable String entityId) {
        authService.require(request, "metadata:read");
        mark(request, entityType, entityId);
        return metadataService.readArtifact(entityType, entityId);
    }

    @GetMapping("/audit")
    public ApiModels.AuditList audit(HttpServletRequest request) {
        authService.require(request, "metadata:read");
        return auditService.list();
    }

    @GetMapping("/boundary")
    public ApiModels.Boundary boundary(HttpServletRequest request) {
        authService.require(request, "metadata:read");
        return capabilities();
    }

    private ApiModels.MetadataList list(HttpServletRequest request, String entityType) {
        authService.require(request, "metadata:read");
        return metadataService.list(entityType);
    }

    private ApiModels.MetadataView get(HttpServletRequest request, String entityType, String entityId) {
        authService.require(request, "metadata:read");
        mark(request, entityType, entityId);
        return metadataService.get(entityType, entityId);
    }

    private static void mark(HttpServletRequest request, ApiModels.IngestManifest manifest) {
        if (manifest != null) mark(request, manifest.entityType(), manifest.entityId());
    }

    private static void mark(HttpServletRequest request, String entityType, String entityId) {
        request.setAttribute("rpf.control-plane.entity-type", normalize(entityType));
        request.setAttribute("rpf.control-plane.entity-id", entityId);
    }

    private static String normalize(String value) {
        return value == null ? null : value.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
