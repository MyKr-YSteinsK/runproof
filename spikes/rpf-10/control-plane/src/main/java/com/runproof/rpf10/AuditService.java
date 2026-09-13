package com.runproof.rpf10;

import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

/** Stores only non-secret audit identity; bearer material is never accepted. */
@Service
public class AuditService {

    private final JdbcTemplate jdbcTemplate;

    public AuditService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void record(String principalId, String action, String entityId, String result, String requestId) {
        try {
            jdbcTemplate.update(
                    "INSERT INTO control_plane_audit(principal_id, action, entity_id, result, request_id, occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
                    principalId,
                    action,
                    entityId,
                    result,
                    requestId,
                    Timestamp.from(Instant.now())
            );
        } catch (DataAccessException ignored) {
            // Audit availability must not turn a DB outage into a fake Agent FAIL.
        }
    }

    public ApiModels.AuditList list() {
        List<ApiModels.AuditEvent> events = jdbcTemplate.query(
                "SELECT audit_id, principal_id, action, entity_id, result, request_id, occurred_at FROM control_plane_audit ORDER BY audit_id",
                (rs, rowNum) -> new ApiModels.AuditEvent(
                        rs.getLong("audit_id"),
                        rs.getString("principal_id"),
                        rs.getString("action"),
                        rs.getString("entity_id"),
                        rs.getString("result"),
                        rs.getString("request_id"),
                        rs.getTimestamp("occurred_at").toInstant().toString()
                )
        );
        return new ApiModels.AuditList(events);
    }
}
