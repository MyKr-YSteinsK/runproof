package com.runproof.rpf09;

import jakarta.annotation.PostConstruct;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Explicit, tiny migration for the investigation candidate. */
@Component
public class PersistenceSchema {

    public static final String SCHEMA_VERSION = "rpf-09-metadata-schema-v1";

    private final JdbcTemplate jdbcTemplate;
    private volatile boolean ready;

    public PersistenceSchema(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @PostConstruct
    public void migrate() {
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS rpf_schema_history (
                    version VARCHAR(128) PRIMARY KEY,
                    applied_at VARCHAR(64) NOT NULL
                )
                """);
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS canonical_metadata (
                    entity_type VARCHAR(64) NOT NULL,
                    entity_id VARCHAR(256) NOT NULL,
                    outcome VARCHAR(64) NOT NULL,
                    agent_version VARCHAR(256),
                    evaluation_id VARCHAR(256),
                    artifact_id VARCHAR(256) NOT NULL,
                    artifact_key VARCHAR(512) NOT NULL,
                    artifact_kind VARCHAR(128) NOT NULL,
                    artifact_schema_version VARCHAR(128) NOT NULL,
                    artifact_content_sha256 VARCHAR(64) NOT NULL,
                    artifact_source_sha256 VARCHAR(64) NOT NULL,
                    artifact_runtime_version VARCHAR(128) NOT NULL,
                    idempotency_key VARCHAR(512) NOT NULL,
                    created_at VARCHAR(64) NOT NULL,
                    PRIMARY KEY (entity_type, entity_id),
                    UNIQUE (idempotency_key)
                )
                """);
        Integer applied = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM rpf_schema_history WHERE version = ?",
                Integer.class,
                SCHEMA_VERSION
        );
        if (applied == null || applied == 0) {
            jdbcTemplate.update(
                    "INSERT INTO rpf_schema_history(version, applied_at) VALUES (?, CURRENT_TIMESTAMP)",
                    SCHEMA_VERSION
            );
        }
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
}
