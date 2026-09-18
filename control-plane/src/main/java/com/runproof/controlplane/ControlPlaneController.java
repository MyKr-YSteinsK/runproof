package com.runproof.controlplane;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Autowired;
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
import java.util.Set;

@RestController
@RequestMapping("/api/v1")
public class ControlPlaneController {

    private final PersistenceSchema schema;
    private final LocalFileArtifactStore artifactStore;
    private final CanonicalMetadataService metadataService;
    private final AuditService auditService;
    private final AuthService authService;
    private final ObservabilityService observability;
    private final boolean probeEnabled;

    @Autowired
    public ControlPlaneController(
            PersistenceSchema schema,
            LocalFileArtifactStore artifactStore,
            CanonicalMetadataService metadataService,
            AuditService auditService,
            AuthService authService,
            @Value("${rpf.probe.enabled:false}") boolean probeEnabled,
            ObservabilityService observability
    ) {
        this.schema = schema;
        this.artifactStore = artifactStore;
        this.metadataService = metadataService;
        this.auditService = auditService;
        this.authService = authService;
        this.probeEnabled = probeEnabled;
        this.observability = observability;
    }

    /** Compatibility constructor for focused unit tests that predate RPF-30. */
    public ControlPlaneController(
            PersistenceSchema schema,
            LocalFileArtifactStore artifactStore,
            CanonicalMetadataService metadataService,
            AuditService auditService,
            AuthService authService,
            boolean probeEnabled
    ) {
        this(schema, artifactStore, metadataService, auditService, authService, probeEnabled,
                new ObservabilityService(false, "", "runproof-control-plane-test"));
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
                List.of("metadata:read", "evidence:write", "decision:write", "agent:observe", "execution:submit", "execution:worker"),
                false, false, false, false, false, true, "DURABLE_SUBMIT_POLL_CANONICAL_READBACK"
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
        if ("RELEASE_DECISION".equals(entityType) || "STATISTICAL_RELEASE_DECISION".equals(entityType)) {
            throw new ProbeExceptions.AuthorizationForbiddenException("decision:write");
        }
        Principal principal = authService.require(request, "evidence:write");
        if (failAfterWrite && !probeEnabled) {
            throw new ProbeExceptions.RequestValidationException("PROBE_MODE_REQUIRED", "Controlled rollback mode is disabled.");
        }
        try (ObservabilityService.SpanScope ignored = observability.span("runproof.evidence.ingest", Map.of(
                "runproof.outcome", manifest == null || manifest.outcome() == null ? "UNKNOWN" : manifest.outcome()
        ))) {
            ApiModels.IngestResponse response = metadataService.ingest(manifest, principal.id(), failAfterWrite);
            return ResponseEntity.status(response.alreadyExists() ? HttpStatus.OK : HttpStatus.CREATED).body(response);
        }
    }

    @PostMapping("/release-decisions")
    public ResponseEntity<ApiModels.IngestResponse> registerDecision(
            HttpServletRequest request,
            @RequestBody ApiModels.IngestManifest manifest,
            @RequestParam(name = "fail_after_write", defaultValue = "false") boolean failAfterWrite
    ) {
        mark(request, manifest);
        Principal principal = authService.require(request, "decision:write");
        String decisionEntityType = manifest == null ? "" : normalize(manifest.entityType());
        if (!Set.of("RELEASE_DECISION", "STATISTICAL_RELEASE_DECISION").contains(decisionEntityType)) {
            throw new ProbeExceptions.RequestValidationException("INVALID_DECISION_MANIFEST", "Only Release Decision manifests may use this endpoint.");
        }
        if (failAfterWrite && !probeEnabled) {
            throw new ProbeExceptions.RequestValidationException("PROBE_MODE_REQUIRED", "Controlled rollback mode is disabled.");
        }
        try (ObservabilityService.SpanScope ignored = observability.span("runproof.decision.write", Map.of(
                "runproof.outcome", manifest == null || manifest.outcome() == null ? "UNKNOWN" : manifest.outcome()
        ))) {
            ApiModels.IngestResponse response = metadataService.ingest(manifest, principal.id(), failAfterWrite);
            return ResponseEntity.status(response.alreadyExists() ? HttpStatus.OK : HttpStatus.CREATED).body(response);
        }
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

    @GetMapping("/failure-intelligence")
    public ApiModels.MetadataList failureIntelligence(HttpServletRequest request) {
        return list(request, "FAILURE_INTELLIGENCE");
    }

    @GetMapping("/failure-intelligence/{entityId}")
    public ApiModels.MetadataView failureIntelligenceItem(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "FAILURE_INTELLIGENCE", entityId);
    }

    @GetMapping("/failure-clusters")
    public ApiModels.MetadataList failureClusters(HttpServletRequest request) {
        return list(request, "FAILURE_CLUSTER");
    }

    @GetMapping("/failure-clusters/{entityId}")
    public ApiModels.MetadataView failureCluster(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "FAILURE_CLUSTER", entityId);
    }

    @GetMapping("/version-bisects")
    public ApiModels.MetadataList versionBisects(HttpServletRequest request) {
        return list(request, "VERSION_BISECT");
    }

    @GetMapping("/version-bisects/{entityId}")
    public ApiModels.MetadataView versionBisect(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "VERSION_BISECT", entityId);
    }

    @GetMapping("/statistical-sampling-plans")
    public ApiModels.MetadataList statisticalSamplingPlans(HttpServletRequest request) {
        return list(request, "STATISTICAL_SAMPLING_PLAN");
    }

    @GetMapping("/statistical-sampling-plans/{entityId}")
    public ApiModels.MetadataView statisticalSamplingPlan(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "STATISTICAL_SAMPLING_PLAN", entityId);
    }

    @GetMapping("/statistical-evaluations")
    public ApiModels.MetadataList statisticalEvaluations(HttpServletRequest request) {
        return list(request, "STATISTICAL_EVALUATION");
    }

    @GetMapping("/statistical-evaluations/{entityId}")
    public ApiModels.MetadataView statisticalEvaluation(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "STATISTICAL_EVALUATION", entityId);
    }

    @GetMapping("/statistical-comparisons")
    public ApiModels.MetadataList statisticalComparisons(HttpServletRequest request) {
        return list(request, "STATISTICAL_COMPARISON");
    }

    @GetMapping("/statistical-comparisons/{entityId}")
    public ApiModels.MetadataView statisticalComparison(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "STATISTICAL_COMPARISON", entityId);
    }

    @GetMapping("/statistical-policies")
    public ApiModels.MetadataList statisticalPolicies(HttpServletRequest request) {
        return list(request, "STATISTICAL_POLICY");
    }

    @GetMapping("/statistical-policies/{entityId}")
    public ApiModels.MetadataView statisticalPolicy(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "STATISTICAL_POLICY", entityId);
    }

    @GetMapping("/statistical-gates")
    public ApiModels.MetadataList statisticalGates(HttpServletRequest request) {
        return list(request, "STATISTICAL_GATE");
    }

    @GetMapping("/statistical-gates/{entityId}")
    public ApiModels.MetadataView statisticalGate(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "STATISTICAL_GATE", entityId);
    }

    @GetMapping("/statistical-release-decisions")
    public ApiModels.MetadataList statisticalReleaseDecisions(HttpServletRequest request) {
        return list(request, "STATISTICAL_RELEASE_DECISION");
    }

    @GetMapping("/statistical-release-decisions/{entityId}")
    public ApiModels.MetadataView statisticalReleaseDecision(HttpServletRequest request, @PathVariable String entityId) {
        return get(request, "STATISTICAL_RELEASE_DECISION", entityId);
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
        String spanName = "RELEASE_DECISION".equals(entityType) || "STATISTICAL_RELEASE_DECISION".equals(entityType)
                ? "runproof.decision.read" : "runproof.canonical.read";
        try (ObservabilityService.SpanScope ignored = observability.span(spanName, Map.of("runproof.target.type", entityType))) {
            return metadataService.list(entityType);
        }
    }

    private ApiModels.MetadataView get(HttpServletRequest request, String entityType, String entityId) {
        authService.require(request, "metadata:read");
        mark(request, entityType, entityId);
        String spanName = "RELEASE_DECISION".equals(entityType) || "STATISTICAL_RELEASE_DECISION".equals(entityType)
                ? "runproof.decision.read" : "runproof.canonical.read";
        try (ObservabilityService.SpanScope ignored = observability.span(spanName, Map.of("runproof.target.type", entityType))) {
            return metadataService.get(entityType, entityId);
        }
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
