package com.runproof.rpf13;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

/** Explicit PostgreSQL migration for the RPF-13 durable execution candidate. */
@Component
public class PersistenceSchema {

    public static final String SCHEMA_VERSION = "rpf-13-durable-execution-schema-v1";

    private final JdbcTemplate jdbcTemplate;
    private final DataSource dataSource;
    private final String configuredSchemaVersion;
    private volatile boolean ready;
    private volatile DatabaseIdentity databaseIdentity = DatabaseIdentity.unknown();

    public PersistenceSchema(
            JdbcTemplate jdbcTemplate,
            DataSource dataSource,
            @Value("${rpf.persistence.schema-version:" + SCHEMA_VERSION + "}") String configuredSchemaVersion
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.dataSource = dataSource;
        this.configuredSchemaVersion = configuredSchemaVersion;
    }

    @PostConstruct
    public void migrate() {
        if (!SCHEMA_VERSION.equals(configuredSchemaVersion)) {
            throw new IllegalStateException("Unsupported configured RPF-13 schema version; startup is blocked.");
        }
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS rpf_schema_history (
                    version VARCHAR(128) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL
                )
                """);
        List<String> versions = jdbcTemplate.query(
                "SELECT version FROM rpf_schema_history ORDER BY applied_at, version",
                (rs, rowNum) -> rs.getString("version")
        );
        if (versions.stream().anyMatch(version -> !SCHEMA_VERSION.equals(version))) {
            throw new IllegalStateException("Unsupported RPF schema history; startup is blocked.");
        }

        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS rpf_execution_job (
                    job_id VARCHAR(256) PRIMARY KEY,
                    idempotency_key VARCHAR(512) NOT NULL UNIQUE,
                    request_fingerprint VARCHAR(128) NOT NULL,
                    job_type VARCHAR(64) NOT NULL,
                    target_type VARCHAR(64) NOT NULL,
                    target_id VARCHAR(256) NOT NULL,
                    payload_ref_json TEXT NOT NULL,
                    correlation_id VARCHAR(256) NOT NULL,
                    state VARCHAR(64) NOT NULL,
                    version BIGINT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    active_attempt_id VARCHAR(256),
                    active_worker_id VARCHAR(256),
                    active_lease_token_hash VARCHAR(128),
                    lease_expires_at TIMESTAMPTZ,
                    heartbeat_at TIMESTAMPTZ,
                    cancel_requested BOOLEAN NOT NULL,
                    timeout_requested BOOLEAN NOT NULL,
                    outcome_status VARCHAR(64),
                    platform_reason VARCHAR(256),
                    terminal_evidence_id VARCHAR(256),
                    last_operation_id VARCHAR(256),
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    CONSTRAINT rpf_execution_job_state_ck CHECK (
                        state IN ('QUEUED', 'CLAIMED', 'RUNNING', 'CANCEL_REQUESTED', 'RECONCILE_REQUIRED', 'COMPLETED', 'FAILED_PLATFORM', 'CANCELLED')
                    )
                )
                """);
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS rpf_execution_attempt (
                    attempt_id VARCHAR(256) PRIMARY KEY,
                    job_id VARCHAR(256) NOT NULL REFERENCES rpf_execution_job(job_id),
                    attempt_number INTEGER NOT NULL,
                    worker_id VARCHAR(256) NOT NULL,
                    lease_token_hash VARCHAR(128) NOT NULL,
                    lease_version BIGINT NOT NULL,
                    status VARCHAR(64) NOT NULL,
                    lease_expires_at TIMESTAMPTZ NOT NULL,
                    heartbeat_at TIMESTAMPTZ,
                    started_at TIMESTAMPTZ,
                    ended_at TIMESTAMPTZ,
                    reason VARCHAR(256),
                    created_at TIMESTAMPTZ NOT NULL,
                    UNIQUE (job_id, attempt_number)
                )
                """);
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS rpf_execution_operation (
                    operation_id VARCHAR(256) PRIMARY KEY,
                    job_id VARCHAR(256) NOT NULL REFERENCES rpf_execution_job(job_id),
                    attempt_id VARCHAR(256) NOT NULL REFERENCES rpf_execution_attempt(attempt_id),
                    environment_id VARCHAR(256) NOT NULL,
                    operation_fingerprint VARCHAR(128) NOT NULL,
                    status VARCHAR(64) NOT NULL,
                    effect_count INTEGER NOT NULL,
                    receipt_ref VARCHAR(256),
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    UNIQUE (job_id, operation_id)
                )
                """);
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS rpf_simulated_effect (
                    operation_id VARCHAR(256) PRIMARY KEY REFERENCES rpf_execution_operation(operation_id),
                    job_id VARCHAR(256) NOT NULL REFERENCES rpf_execution_job(job_id),
                    environment_id VARCHAR(256) NOT NULL,
                    receipt_ref VARCHAR(256) NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL
                )
                """);
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS rpf_execution_evidence (
                    evidence_id VARCHAR(256) PRIMARY KEY,
                    job_id VARCHAR(256) NOT NULL REFERENCES rpf_execution_job(job_id),
                    entity_type VARCHAR(64) NOT NULL,
                    entity_id VARCHAR(256) NOT NULL,
                    outcome VARCHAR(64) NOT NULL,
                    content_sha256 VARCHAR(128) NOT NULL,
                    artifact_ref_json TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    UNIQUE (job_id, entity_type, entity_id)
                )
                """);
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS rpf_execution_event (
                    event_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    job_id VARCHAR(256) NOT NULL REFERENCES rpf_execution_job(job_id),
                    from_state VARCHAR(64),
                    to_state VARCHAR(64) NOT NULL,
                    event_type VARCHAR(128) NOT NULL,
                    attempt_id VARCHAR(256),
                    operation_id VARCHAR(256),
                    reason VARCHAR(256),
                    version BIGINT NOT NULL,
                    occurred_at TIMESTAMPTZ NOT NULL
                )
                """);

        if (versions.isEmpty()) {
            jdbcTemplate.update(
                    "INSERT INTO rpf_schema_history(version, applied_at) VALUES (?, ?)",
                    SCHEMA_VERSION,
                    Timestamp.from(Instant.now())
            );
        }
        databaseIdentity = readDatabaseIdentity();
        ready = true;
    }

    public boolean isReady() {
        return ready;
    }

    public boolean databaseResponding() {
        try {
            Integer result = jdbcTemplate.queryForObject("SELECT 1", Integer.class);
            return result != null && result == 1;
        } catch (RuntimeException ignored) {
            return false;
        }
    }

    public DatabaseIdentity databaseIdentity() {
        return databaseIdentity;
    }

    private DatabaseIdentity readDatabaseIdentity() {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData metadata = connection.getMetaData();
            return new DatabaseIdentity(
                    metadata.getDatabaseProductName(),
                    metadata.getDatabaseProductVersion(),
                    metadata.getDriverName(),
                    metadata.getDriverVersion(),
                    connection.getCatalog() == null ? "unknown" : connection.getCatalog(),
                    connection.getSchema() == null ? "unknown" : connection.getSchema()
            );
        } catch (SQLException exception) {
            throw new IllegalStateException("Cannot inspect PostgreSQL identity.", exception);
        }
    }

    public record DatabaseIdentity(
            String product,
            String version,
            String jdbcDriver,
            String jdbcDriverVersion,
            String databaseName,
            String schema
    ) {
        static DatabaseIdentity unknown() {
            return new DatabaseIdentity("UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN");
        }
    }
}
