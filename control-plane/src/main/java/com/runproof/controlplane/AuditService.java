package com.runproof.controlplane;

import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

@Service
public class AuditService {

    private final JdbcTemplate jdbcTemplate;

    public AuditService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void record(String principalId, String action, String entityType, String entityId, String result, String requestId, String reasonCode) {
        try {
            jdbcTemplate.update(
                    "INSERT INTO control_plane_audit(principal_id, action, entity_type, entity_id, result, request_id, reason_code, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    safe(principalId, 128), safe(action, 256), safe(entityType, 64), safe(entityId, 256),
                    safe(result, 128), safe(requestId, 128), safe(reasonCode, 128), Timestamp.from(Instant.now())
            );
        } catch (DataAccessException ignored) {
            // Audit failure must not turn a platform/storage problem into Agent FAIL.
        }
    }

    public ApiModels.AuditList list() {
        List<ApiModels.AuditEvent> events = jdbcTemplate.query(
                "SELECT audit_id, principal_id, action, entity_type, entity_id, result, request_id, reason_code, occurred_at FROM control_plane_audit ORDER BY audit_id",
                (rs, rowNum) -> new ApiModels.AuditEvent(
                        rs.getLong("audit_id"),
                        rs.getString("principal_id"),
                        rs.getString("action"),
                        rs.getString("entity_type"),
                        rs.getString("entity_id"),
                        rs.getString("result"),
                        rs.getString("request_id"),
                        rs.getString("reason_code"),
                        rs.getObject("occurred_at", java.time.OffsetDateTime.class).toInstant().toString()
                )
        );
        return new ApiModels.AuditList(events);
    }

    private static String safe(String value, int max) {
        if (value == null || value.isBlank() || "null".equals(value)) return null;
        return value.length() <= max ? value : value.substring(0, max);
    }
}
