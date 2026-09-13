package com.runproof.rpf09;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/** Small synchronous HTTP/JSON boundary used only by the RPF-09 probe. */
@RestController
@RequestMapping("/api/v1")
public class ControlPlaneController {

    private final PersistenceSchema persistenceSchema;
    private final CanonicalMetadataService metadataService;
    private final ConfigurableApplicationContext applicationContext;

    public ControlPlaneController(
            PersistenceSchema persistenceSchema,
            CanonicalMetadataService metadataService,
            ConfigurableApplicationContext applicationContext
    ) {
        this.persistenceSchema = persistenceSchema;
        this.metadataService = metadataService;
        this.applicationContext = applicationContext;
    }

    @GetMapping("/health")
    public ResponseEntity<ApiModels.HealthResponse> health() {
        boolean databaseReady = persistenceSchema.isReady() && persistenceSchema.databaseResponding();
        ApiModels.HealthResponse response = new ApiModels.HealthResponse(
                databaseReady ? "UP" : "DOWN",
                databaseReady ? "READY" : "NOT_READY",
                databaseReady ? "RESPONDING" : "UNAVAILABLE",
                PersistenceSchema.SCHEMA_VERSION
        );
        return ResponseEntity.status(databaseReady ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE).body(response);
    }

    @PostMapping("/ingest/completed-evidence")
    public ResponseEntity<ApiModels.IngestResponse> ingest(
            @RequestBody ApiModels.IngestManifest manifest,
            @RequestParam(name = "fail_after_write", defaultValue = "false") boolean failAfterWrite
    ) {
        ApiModels.IngestResponse response = metadataService.ingest(manifest, failAfterWrite);
        return ResponseEntity.status(response.alreadyExists() ? HttpStatus.OK : HttpStatus.CREATED).body(response);
    }

    @GetMapping("/metadata/{entityType}/{entityId}")
    public ApiModels.MetadataView metadata(
            @PathVariable String entityType,
            @PathVariable String entityId
    ) {
        return metadataService.get(entityType, entityId);
    }

    @GetMapping("/runs/{entityId}")
    public ApiModels.MetadataView run(@PathVariable String entityId) {
        return metadataService.get("RUN", entityId);
    }

    @GetMapping("/evaluations/{entityId}")
    public ApiModels.MetadataView evaluation(@PathVariable String entityId) {
        return metadataService.get("EVALUATION", entityId);
    }

    @GetMapping("/release-decisions/{entityId}")
    public ApiModels.MetadataView releaseDecision(@PathVariable String entityId) {
        return metadataService.get("RELEASE_DECISION", entityId);
    }

    @GetMapping("/release-decisions")
    public ApiModels.MetadataList releaseDecisions() {
        return metadataService.list("RELEASE_DECISION");
    }

    @GetMapping("/probe/boundary")
    public Map<String, Object> boundary() {
        return Map.of(
                "transport", "SYNCHRONOUS_HTTP_JSON",
                "job_transport_resolved", false,
                "queue_or_broker", false,
                "release_or_deploy_authorized", false
        );
    }

    /** Probe-only graceful shutdown so restart evidence closes the real JVM. */
    @PostMapping("/probe/shutdown")
    public Map<String, String> shutdown() {
        Thread shutdown = new Thread(() -> {
            try {
                Thread.sleep(100);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
            int exitCode = SpringApplication.exit(applicationContext);
            System.exit(exitCode);
        }, "rpf09-probe-shutdown");
        shutdown.setDaemon(true);
        shutdown.start();
        return Map.of("status", "SHUTTING_DOWN");
    }
}
