package com.runproof.controlplane;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static com.runproof.controlplane.ProbeExceptions.EntityNotFoundException;
import static com.runproof.controlplane.ProbeExceptions.IdentityConflictException;
import static com.runproof.controlplane.ProbeExceptions.InvalidEvidenceException;
import static com.runproof.controlplane.ProbeExceptions.ProbeRollbackException;
import static com.runproof.controlplane.ProbeExceptions.RequestValidationException;

@Service
public class CanonicalMetadataService {

    private static final String MANIFEST_SCHEMA = "rpf-canonical-ingest-v1";
    static final String METADATA_CURSOR_CONTRACT = "rpf-metadata-cursor-v1";
    static final int METADATA_DEFAULT_LIMIT = 50;
    static final int METADATA_MAX_LIMIT = 100;
    private static final String METADATA_ORDER_BY_TYPE = "created_at,entity_id:asc";
    private static final String METADATA_ORDER_CROSS_TYPE = "created_at,entity_type,entity_id:asc";
    private static final String LEGACY_RPF18_SOURCE_SHA256 = "3a1083279be0e6969c7222e86087647058e5a15562c1f99eccdc4297a21bd689";
    private static final List<String> DECISION_ROLES = List.of(
            "policy_ref", "suite_ref", "candidate_evaluation_ref", "comparison_ref", "gate_evaluation_ref", "regression_ref"
    );
    private static final List<String> STATISTICAL_DECISION_ROLES = List.of(
            "policy_ref", "sampling_plan_ref", "evaluation_ref"
    );

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;
    private final ArtifactStore artifactStore;

    public CanonicalMetadataService(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper, ArtifactStore artifactStore) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
        this.artifactStore = artifactStore;
    }

    @Transactional
    public ApiModels.IngestResponse ingest(ApiModels.IngestManifest manifest, String principalId, boolean failAfterWrite) {
        NormalizedManifest normalized = validate(manifest, principalId);
        JsonNode artifact = artifactStore.readVerifiedArtifact(
                normalized.artifactRef(), normalized.entityType(), normalized.entityId()
        ).document();
        validateArtifactSemantics(artifact, normalized);
        if ("RELEASE_DECISION".equals(normalized.entityType())) {
            validateDecisionReferences(normalized.keyRefs());
            if (normalized.supersedesEntityId() != null && !normalized.supersedesEntityId().isBlank()
                    && !has("RELEASE_DECISION", normalized.supersedesEntityId())) {
                throw new InvalidEvidenceException("INVALID_DECISION_HISTORY", "Release Decision supersedes an unavailable decision.");
            }
        } else if ("STATISTICAL_RELEASE_DECISION".equals(normalized.entityType())) {
            validateStatisticalDecisionReferences(normalized.keyRefs(), artifact);
            if (normalized.supersedesEntityId() != null && !normalized.supersedesEntityId().isBlank()
                    && !has("STATISTICAL_RELEASE_DECISION", normalized.supersedesEntityId())) {
                throw new InvalidEvidenceException("INVALID_DECISION_HISTORY", "Statistical Release Decision supersedes an unavailable decision.");
            }
        }

        MetadataRow existing = find(normalized.entityType(), normalized.entityId());
        if (existing != null) {
            return replayOrConflict(existing, normalized);
        }
        MetadataRow idempotencyOwner = findByIdempotency(normalized.idempotencyKey());
        if (idempotencyOwner != null) {
            throw new IdentityConflictException("The idempotency key belongs to a different immutable entity.");
        }

        String summaryJson = json(normalized.summary());
        String refsJson = json(normalized.keyRefs());
        int inserted = jdbcTemplate.update("""
                    INSERT INTO canonical_metadata(
                        entity_type, entity_id, entity_schema_version, artifact_kind, outcome,
                        agent_version, evaluation_id, source_sha256, runtime_version,
                        summary_json, key_refs_json, artifact_id, artifact_key, artifact_schema_version,
                        artifact_content_sha256, artifact_source_sha256, artifact_runtime_version,
                        idempotency_key, supersedes_entity_id, registered_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    normalized.entityType(), normalized.entityId(), normalized.entitySchemaVersion(), normalized.artifactRef().artifactKind(),
                    normalized.outcome(), normalized.agentVersion(), normalized.evaluationId(), normalized.sourceIdentity().sourceSha256(),
                    normalized.sourceIdentity().runtimeVersion(), summaryJson, refsJson,
                    normalized.artifactRef().artifactId(), normalized.artifactRef().artifactKey(), normalized.artifactRef().schemaVersion(),
                    normalized.artifactRef().contentSha256(), normalized.artifactRef().sourceSha256(), normalized.artifactRef().runtimeVersion(),
                    normalized.idempotencyKey(), normalized.supersedesEntityId(), normalized.principalId(), Timestamp.from(Instant.now())
            );
        if (inserted == 0) {
            MetadataRow raced = find(normalized.entityType(), normalized.entityId());
            if (raced != null) return replayOrConflict(raced, normalized);
            MetadataRow owner = findByIdempotency(normalized.idempotencyKey());
            if (owner != null) {
                throw new IdentityConflictException("The idempotency key belongs to a different immutable entity.");
            }
            throw new IllegalStateException("Canonical insert conflicted without a readable owner row.");
        }

        if (failAfterWrite) {
            throw new ProbeRollbackException();
        }
        MetadataRow created = find(normalized.entityType(), normalized.entityId());
        if (created == null) {
            throw new IllegalStateException("Canonical row was not readable after insert.");
        }
        return new ApiModels.IngestResponse("INGESTED", false, toView(created));
    }

    public ApiModels.MetadataView get(String entityType, String entityId) {
        return get(entityType, entityId, true);
    }

    public ApiModels.MetadataView get(String entityType, String entityId, boolean verifyArtifact) {
        MetadataRow row = find(normalizeEntityType(entityType), entityId);
        if (row == null) throw new EntityNotFoundException("Canonical metadata was not found.");
        return toView(row, verifyArtifact);
    }

    public ApiModels.MetadataList list(String entityType) {
        return list(entityType, null, null);
    }

    public ApiModels.MetadataList list(String entityType, Integer requestedLimit, String encodedCursor) {
        String normalized = normalizeEntityType(entityType);
        int limit = boundedLimit(requestedLimit);
        String ordering = normalized == null ? METADATA_ORDER_CROSS_TYPE : METADATA_ORDER_BY_TYPE;
        MetadataCursor cursor = decodeCursor(encodedCursor);
        validateCursor(cursor, normalized, ordering, limit);

        StringBuilder sql = new StringBuilder("SELECT * FROM canonical_metadata");
        List<Object> arguments = new ArrayList<>();
        if (normalized != null) {
            sql.append(" WHERE entity_type = ?");
            arguments.add(normalized);
            if (cursor != null) {
                sql.append(" AND (created_at > ? OR (created_at = ? AND entity_id > ?))");
                Timestamp timestamp = cursorTimestamp(cursor);
                arguments.add(timestamp);
                arguments.add(timestamp);
                arguments.add(cursor.entityId());
            }
            sql.append(" ORDER BY created_at ASC, entity_id ASC LIMIT ?");
        } else {
            if (cursor != null) {
                sql.append(" WHERE (created_at > ? OR (created_at = ? AND (entity_type > ? OR (entity_type = ? AND entity_id > ?))))");
                Timestamp timestamp = cursorTimestamp(cursor);
                arguments.add(timestamp);
                arguments.add(timestamp);
                arguments.add(cursor.entityType());
                arguments.add(cursor.entityType());
                arguments.add(cursor.entityId());
            }
            sql.append(" ORDER BY created_at ASC, entity_type ASC, entity_id ASC LIMIT ?");
        }
        arguments.add(limit + 1);
        List<MetadataRow> rows = jdbcTemplate.query(sql.toString(), rowMapper(), arguments.toArray());
        boolean hasMore = rows.size() > limit;
        if (hasMore) rows = new ArrayList<>(rows.subList(0, limit));
        String nextCursor = hasMore && !rows.isEmpty() ? encodeCursor(normalized, ordering, limit, rows.get(rows.size() - 1)) : null;
        return new ApiModels.MetadataList(
                rows.stream().map(row -> toView(row, false)).toList(),
                limit,
                hasMore,
                nextCursor == null ? NullNode.getInstance() : objectMapper.getNodeFactory().textNode(nextCursor),
                METADATA_CURSOR_CONTRACT,
                ordering,
                normalized,
                "REGISTERED_REFERENCE"
        );
    }

    public ApiModels.ArtifactResponse readArtifact(String entityType, String entityId) {
        MetadataRow row = find(normalizeEntityType(entityType), entityId);
        if (row == null) throw new EntityNotFoundException("Canonical metadata was not found.");
        ArtifactStore.VerifiedArtifact verified = artifactStore.readVerifiedArtifact(row.artifactRef(), row.entityType(), row.entityId());
        return new ApiModels.ArtifactResponse(verified.snapshot(), verified.document());
    }

    public boolean has(String entityType, String entityId) {
        return find(normalizeEntityType(entityType), entityId) != null;
    }

    private ApiModels.IngestResponse replayOrConflict(MetadataRow existing, NormalizedManifest incoming) {
        if (sameFingerprint(existing, incoming)) {
            return new ApiModels.IngestResponse("IDEMPOTENT_REPLAY", true, toView(existing));
        }
        throw new IdentityConflictException("The immutable entity identity already contains different content.");
    }

    private NormalizedManifest validate(ApiModels.IngestManifest manifest, String principalId) {
        if (manifest == null) throw new RequestValidationException("INVALID_MANIFEST", "Ingest manifest is required.");
        if (!MANIFEST_SCHEMA.equals(manifest.manifestSchemaVersion())) {
            throw new RequestValidationException("UNKNOWN_MANIFEST_SCHEMA", "Manifest schema is not accepted.");
        }
        String entityType = normalizeEntityType(manifest.entityType());
        if (entityType == null || !ArtifactStoreSupport.supports(entityType)) {
            throw new RequestValidationException("UNSUPPORTED_ENTITY_TYPE", "Entity type is not supported.");
        }
        requireText(manifest.entityId(), "entity_id");
        requireText(manifest.entitySchemaVersion(), "entity_schema_version");
        requireText(manifest.outcome(), "outcome");
        requireText(manifest.idempotencyKey(), "idempotency_key");
        if (manifest.entitySchemaVersion() == null || !manifest.entitySchemaVersion().equals(ArtifactStoreSupport.expectedSchema(entityType))) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_UNKNOWN_SCHEMA", "Entity schema does not match its artifact contract.");
        }
        ApiModels.ArtifactRef artifactRef = manifest.artifactRef();
        ApiModels.SourceIdentity source = manifest.sourceIdentity();
        if (source == null) {
            source = new ApiModels.SourceIdentity(artifactRef == null ? null : artifactRef.sourceSha256(), artifactRef == null ? null : artifactRef.runtimeVersion());
        }
        if (artifactRef == null || source.sourceSha256() == null || source.runtimeVersion() == null
                || !Objects.equals(source.sourceSha256(), artifactRef.sourceSha256())
                || !Objects.equals(source.runtimeVersion(), artifactRef.runtimeVersion())) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_SOURCE_IDENTITY", "Manifest source identity does not match its artifact reference.");
        }
        List<ApiModels.EntityRef> keyRefs = manifest.keyRefs() == null ? List.of() : List.copyOf(manifest.keyRefs());
        Map<String, Object> summary = manifest.summary() == null ? Map.of() : Map.copyOf(manifest.summary());
        validateMetadataPayload(summary, keyRefs);
        return new NormalizedManifest(
                entityType, manifest.entityId(), manifest.entitySchemaVersion(), manifest.outcome(), manifest.agentVersion(),
                manifest.evaluationId(), manifest.idempotencyKey(), manifest.supersedesEntityId(), source, keyRefs, summary,
                artifactRef, principalId == null || principalId.isBlank() ? "unknown" : principalId
        );
    }

    private void validateArtifactSemantics(JsonNode artifact, NormalizedManifest manifest) {
        if ("STATISTICAL_EVALUATION".equals(manifest.entityType())) {
            validateStatisticalEvaluationArtifact(artifact);
            return;
        }
        if ("STATISTICAL_GATE".equals(manifest.entityType())) {
            validateStatisticalGateReferences(artifact);
            return;
        }
        if (!Set.of("RELEASE_DECISION", "STATISTICAL_RELEASE_DECISION").contains(manifest.entityType())) return;
        String container = "RELEASE_DECISION".equals(manifest.entityType()) ? "release_decision" : "statistical_release_decision";
        JsonNode decision = artifact.path(container);
        if (!decision.isObject()) throw new InvalidEvidenceException("INVALID_DECISION_ARTIFACT", "Release Decision artifact is missing its decision object.");
        String status = text(decision, "decision_status");
        if (!List.of("ELIGIBLE", "BLOCKED", "REVIEW_REQUIRED", "INCONCLUSIVE").contains(status)) {
            throw new InvalidEvidenceException("INVALID_DECISION_STATUS", "Release Decision status is not accepted.");
        }
        JsonNode boundary = decision.path("authorization_boundary");
        boolean decisionOnly = !boundary.isObject() || !Boolean.FALSE.equals(boolOrNull(boundary, "release_executed"))
                || !Boolean.FALSE.equals(boolOrNull(boundary, "deployment_authorized"));
        if ("STATISTICAL_RELEASE_DECISION".equals(manifest.entityType())) {
            decisionOnly = decisionOnly || !"DECISION_ONLY".equals(text(boundary, "release_action"));
        }
        if (decisionOnly) {
            throw new InvalidEvidenceException("INVALID_RELEASE_AUTHORITY_BOUNDARY", "Release Decision is not decision-only.");
        }
        if (!Boolean.TRUE.equals(boolOrNull(decision.path("history"), "immutable"))) {
            throw new InvalidEvidenceException("INVALID_DECISION_HISTORY", "Release Decision history must be immutable.");
        }
        if ("STATISTICAL_RELEASE_DECISION".equals(manifest.entityType())) {
            JsonNode evaluationSource = decision.get("evaluation_source_identity");
            if (evaluationSource != null && !evaluationSource.isObject()) {
                throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Statistical Release Decision evaluation source identity is malformed.");
            }
            if (evaluationSource != null && (!isSha256(text(evaluationSource, "source_sha256")) || text(evaluationSource, "runtime_version").isBlank())) {
                throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Statistical Release Decision evaluation source identity is malformed.");
            }
        }
    }

    /**
     * Validate the raw statistical Evaluation before it becomes canonical
     * metadata.  The runtime validator remains the detailed implementation
     * contract; this server-side check deliberately covers the security
     * boundary again so a caller cannot register a forged summary and then
     * ask a trusted decision writer to promote it.
     */
    private void validateStatisticalEvaluationArtifact(JsonNode artifact) {
        JsonNode evaluation = artifact == null ? null : artifact.get("statistical_evaluation");
        if (evaluation == null || !evaluation.isObject()) invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation is missing its evaluation object.");
        String evaluationStatus = text(evaluation, "evaluation_status");
        if (!Set.of("COMPLETE", "INCONCLUSIVE", "INVALID").contains(evaluationStatus)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation status is not accepted.");
        }
        if ("INVALID".equals(evaluationStatus)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "An INVALID Statistical Evaluation cannot become canonical decision input.");
        }

        JsonNode source = evaluation.get("source_identity");
        String sourceSha = text(source, "source_sha256");
        if (!isSha256(sourceSha) || text(source, "runtime_version").isBlank()) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation source identity is malformed.");
        }
        JsonNode planRef = evaluation.get("sampling_plan_ref");
        String planId = text(planRef, "sampling_plan_id");
        String planVersion = text(planRef, "sampling_plan_version");
        if (planRef == null || !planRef.isObject() || !"Statistical Sampling Plan".equals(text(planRef, "kind"))
                || planId.isBlank() || planVersion.isBlank()) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation sampling plan reference is malformed.");
        }
        JsonNode planArtifact = canonicalArtifact("STATISTICAL_SAMPLING_PLAN", planId, "Statistical Evaluation sampling plan");
        JsonNode plan = planArtifact.get("sampling_plan");
        if (plan == null || !plan.isObject()) invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Referenced Sampling Plan is malformed.");
        if (!Objects.equals(planId, text(plan, "sampling_plan_id"))
                || !Objects.equals(planVersion, text(plan, "sampling_plan_version"))
                || !Objects.equals(text(plan, "sampling_plan_identity"), text(evaluation, "sampling_plan_identity"))
                || !Objects.equals(text(plan, "candidate_identity"), text(evaluation, "candidate_identity"))
                || !Objects.equals(text(plan, "compatibility_key"), text(evaluation, "compatibility_key"))) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation does not bind its canonical Sampling Plan identity.");
        }
        if (!sameScenarioCore(evaluation.get("scenario_ref"), plan.get("scenario_ref"))
                || !sameAgentBase(evaluation.get("agent"), plan.get("agent"))) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation agent or scenario is incompatible with its Sampling Plan.");
        }
        if (!"fresh-per-trial".equals(text(evaluation, "trial_isolation_policy"))) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation must preserve fresh-per-trial isolation.");
        }

        JsonNode compatibility = evaluation.get("sampling_plan_compatibility");
        boolean legacy = LEGACY_RPF18_SOURCE_SHA256.equals(sourceSha);
        if (compatibility == null || compatibility.isNull()) {
            if (!legacy) invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation is missing its Sampling Plan compatibility contract.");
        } else {
            validateSamplingCompatibility(compatibility, plan, evaluation);
        }

        JsonNode trials = evaluation.get("trials");
        if (trials == null || !trials.isArray()) invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation trials must be an array.");
        List<String> outcomes = List.of("AGENT_PASS", "AGENT_FAIL", "PLATFORM_ERROR", "ENVIRONMENT_ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED");
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String outcome : outcomes) counts.put(outcome, 0);
        Set<String> trialIds = new HashSet<>();
        Set<Integer> trialIndexes = new HashSet<>();
        Set<String> runIds = new HashSet<>();
        Set<String> environmentIds = new HashSet<>();
        int evidenceValidCount = 0;
        for (JsonNode trial : trials) {
            if (trial == null || !trial.isObject()) invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation contains a malformed Trial.");
            String trialId = text(trial, "trial_id");
            Integer trialIndex = integer(trial.get("trial_index"));
            String outcome = text(trial, "outcome");
            if (trialId.isBlank() || trialIndex == null || trialIndex < 1 || !trialIds.add(trialId) || !trialIndexes.add(trialIndex)
                    || !counts.containsKey(outcome)
                    || !Objects.equals(text(trial, "trial_identity"), String.format(Locale.ROOT, "%s:%03d", planId, trialIndex))) {
                invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation Trial identity or outcome is invalid.");
            }
            JsonNode trialPlanRef = trial.get("sampling_plan_ref");
            if (trialPlanRef == null || !trialPlanRef.isObject() || !"Statistical Sampling Plan".equals(text(trialPlanRef, "kind"))
                    || !Objects.equals(planId, text(trialPlanRef, "sampling_plan_id"))
                    || !Objects.equals(planVersion, text(trialPlanRef, "sampling_plan_version"))) {
                invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation Trial has an incompatible Sampling Plan reference.");
            }
            JsonNode runRef = trial.get("run_ref");
            String runId = text(runRef, "run_id");
            if (runRef == null || !runRef.isObject() || !"Run Evidence".equals(text(runRef, "kind")) || runId.isBlank() || !runIds.add(runId)) {
                invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation Trial Run reference is missing or duplicated.");
            }
            // RPF-18 is a preserved historical corpus: its raw controlled
            // Run files live in ignored local evidence and were never part of
            // the shipped canonical seed. New evaluations must resolve every
            // referenced Run through the canonical store.
            if (!legacy) canonicalArtifact("RUN", runId, "Statistical Evaluation Trial Run");
            JsonNode environmentRef = trial.get("environment_ref");
            String environmentId = text(environmentRef, "environment_id");
            if (environmentRef == null || !environmentRef.isObject() || !"Environment".equals(text(environmentRef, "kind"))
                    || environmentId.isBlank() || !environmentIds.add(environmentId)) {
                invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation Trial Environment reference is missing or duplicated.");
            }
            if (!sameAgentBase(trial.get("agent"), evaluation.get("agent"))) {
                invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation Trial Agent identity is incompatible.");
            }
            if (!sameScenarioCore(trial.get("scenario_ref"), evaluation.get("scenario_ref"))) {
                invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation Trial Scenario identity is incompatible.");
            }
            if (!Objects.equals(text(trial, "compatibility_key"), text(evaluation, "compatibility_key"))) {
                invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation Trial compatibility key is incompatible.");
            }
            boolean agentOutcome = Set.of("AGENT_PASS", "AGENT_FAIL").contains(outcome);
            if (!booleanValue(trial.get("agent_quality_eligible"), agentOutcome)
                    || !booleanValue(trial.get("evidence_valid"), agentOutcome)) {
                invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation Trial denominator semantics are inconsistent.");
            }
            if (agentOutcome) evidenceValidCount++;
            counts.put(outcome, counts.get(outcome) + 1);
        }

        int attempted = trials.size();
        int requested = requiredInteger(evaluation.get("requested_trial_count"), "INVALID_STATISTICAL_EVALUATION", "requested_trial_count");
        int expectedRequested = requiredInteger(plan.get("requested_trial_count"), "INVALID_STATISTICAL_EVALUATION", "Sampling Plan requested_trial_count");
        if (requiredInteger(evaluation.get("attempted_trial_count"), "INVALID_STATISTICAL_EVALUATION", "attempted_trial_count") != attempted
                || requested != expectedRequested
                || ("COMPLETE".equals(evaluationStatus) && attempted != requested)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation attempted/requested trial counts are inconsistent.");
        }
        int validAgentCount = counts.get("AGENT_PASS") + counts.get("AGENT_FAIL");
        if (requiredInteger(evaluation.get("valid_agent_trial_count"), "INVALID_STATISTICAL_EVALUATION", "valid_agent_trial_count") != validAgentCount
                || requiredInteger(evaluation.get("evidence_valid_trial_count"), "INVALID_STATISTICAL_EVALUATION", "evidence_valid_trial_count") != evidenceValidCount) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation denominator is inconsistent with raw Trials.");
        }
        JsonNode outcomeCounts = evaluation.get("outcome_counts");
        if (outcomeCounts == null || !outcomeCounts.isObject()) invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation outcome_counts is malformed.");
        for (String outcome : outcomes) {
            if (requiredInteger(outcomeCounts.get(outcome), "INVALID_STATISTICAL_EVALUATION", "outcome_counts." + outcome) != counts.get(outcome)) {
                invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation outcome_counts contradicts raw Trials.");
            }
        }
        validateStatisticalSummary(evaluation, plan, counts, attempted, requested, validAgentCount, evidenceValidCount);
    }

    private void validateSamplingCompatibility(JsonNode compatibility, JsonNode plan, JsonNode evaluation) {
        if (!compatibility.isObject()
                || !Objects.equals(text(compatibility, "sampling_plan_id"), text(plan, "sampling_plan_id"))
                || !Objects.equals(text(compatibility, "sampling_plan_version"), text(plan, "sampling_plan_version"))
                || !Objects.equals(text(compatibility, "sampling_plan_identity"), text(plan, "sampling_plan_identity"))
                || !Objects.equals(text(compatibility, "compatibility_key"), text(plan, "compatibility_key"))
                || !Objects.equals(compatibility.get("suite_ref"), plan.get("suite_ref"))
                || !Objects.equals(compatibility.get("agent"), evaluation.get("agent"))
                || !sameScenarioCore(compatibility.get("scenario_ref"), evaluation.get("scenario_ref"))
                || !Objects.equals(compatibility.get("confidence"), plan.get("confidence"))
                || !Objects.equals(compatibility.get("trial_isolation"), plan.get("trial_isolation"))
                || !Objects.equals(compatibility.get("source_identity"), plan.get("source_identity"))) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation Sampling Plan compatibility does not match the canonical Plan.");
        }
        JsonNode semantics = compatibility.get("sample_semantics");
        if (semantics == null || !semantics.isObject()
                || !"AGENT_PASS + AGENT_FAIL only".equals(text(semantics, "valid_agent_denominator"))
                || !"all attempted trials".equals(text(semantics, "evidence_denominator"))
                || !booleanValue(semantics.get("fresh_environment_per_trial"), true)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation sample semantics are incompatible.");
        }
    }

    private void validateStatisticalSummary(
            JsonNode evaluation,
            JsonNode plan,
            Map<String, Integer> counts,
            int attempted,
            int requested,
            int validAgentCount,
            int evidenceValidCount
    ) {
        JsonNode summary = evaluation.get("summary");
        JsonNode quality = summary == null ? null : summary.get("agent_quality");
        JsonNode interval = quality == null ? null : quality.get("confidence_interval");
        if (summary == null || !summary.isObject() || quality == null || !quality.isObject() || interval == null || !interval.isObject()) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation quality summary is malformed.");
        }
        int pass = counts.get("AGENT_PASS");
        int fail = counts.get("AGENT_FAIL");
        requireIntegerEqual(quality.get("pass_count"), pass, "INVALID_STATISTICAL_EVALUATION", "summary.agent_quality.pass_count");
        requireIntegerEqual(quality.get("fail_count"), fail, "INVALID_STATISTICAL_EVALUATION", "summary.agent_quality.fail_count");
        requireIntegerEqual(quality.get("denominator"), validAgentCount, "INVALID_STATISTICAL_EVALUATION", "summary.agent_quality.denominator");
        Double successRate = validAgentCount == 0 ? null : (double) pass / validAgentCount;
        Double failureRate = validAgentCount == 0 ? null : (double) fail / validAgentCount;
        requireNumberEqual(quality.get("success_rate"), successRate, "INVALID_STATISTICAL_EVALUATION", "summary.agent_quality.success_rate");
        requireNumberEqual(quality.get("failure_rate"), failureRate, "INVALID_STATISTICAL_EVALUATION", "summary.agent_quality.failure_rate");

        String method = text(interval, "method");
        String methodVersion = text(interval, "method_version");
        if (!"WILSON_SCORE".equals(method) || !"wilson-score-v1".equals(methodVersion)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation confidence interval method is unsupported.");
        }
        Double confidenceLevel = decimal(interval.get("confidence_level"));
        Double planConfidence = decimal(plan.path("confidence").get("level"));
        if (confidenceLevel == null || planConfidence == null || !close(confidenceLevel, planConfidence)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation confidence level is incompatible with its Plan.");
        }
        requireIntegerEqual(interval.get("successes"), pass, "INVALID_STATISTICAL_EVALUATION", "confidence_interval.successes");
        requireIntegerEqual(interval.get("trials"), validAgentCount, "INVALID_STATISTICAL_EVALUATION", "confidence_interval.trials");
        Double expectedLower = wilsonBound(pass, validAgentCount, confidenceLevel, false);
        Double expectedUpper = wilsonBound(pass, validAgentCount, confidenceLevel, true);
        requireNumberEqual(interval.get("lower"), expectedLower, "INVALID_STATISTICAL_EVALUATION", "confidence_interval.lower");
        requireNumberEqual(interval.get("upper"), expectedUpper, "INVALID_STATISTICAL_EVALUATION", "confidence_interval.upper");
        String expectedIntervalStatus = validAgentCount == 0 ? "INSUFFICIENT_EVIDENCE" : "COMPLETE";
        if (!Objects.equals(text(interval, "status"), expectedIntervalStatus)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation confidence interval status is inconsistent.");
        }

        JsonNode evidence = summary.get("evidence_quality");
        int platformCount = counts.get("PLATFORM_ERROR") + counts.get("ENVIRONMENT_ERROR");
        requireIntegerEqual(evidence == null ? null : evidence.get("attempted_trials"), attempted, "INVALID_STATISTICAL_EVALUATION", "summary.evidence_quality.attempted_trials");
        requireIntegerEqual(evidence == null ? null : evidence.get("evidence_valid_trial_count"), evidenceValidCount, "INVALID_STATISTICAL_EVALUATION", "summary.evidence_quality.evidence_valid_trial_count");
        requireNumberEqual(evidence == null ? null : evidence.get("evidence_valid_rate"), attempted == 0 ? null : (double) evidenceValidCount / attempted, "INVALID_STATISTICAL_EVALUATION", "summary.evidence_quality.evidence_valid_rate");
        requireIntegerEqual(evidence == null ? null : evidence.get("platform_error_count"), platformCount, "INVALID_STATISTICAL_EVALUATION", "summary.evidence_quality.platform_error_count");
        requireNumberEqual(evidence == null ? null : evidence.get("platform_error_rate"), attempted == 0 ? null : (double) platformCount / attempted, "INVALID_STATISTICAL_EVALUATION", "summary.evidence_quality.platform_error_rate");
        requireIntegerEqual(evidence == null ? null : evidence.get("invalid_count"), counts.get("INVALID"), "INVALID_STATISTICAL_EVALUATION", "summary.evidence_quality.invalid_count");
        requireIntegerEqual(evidence == null ? null : evidence.get("inconclusive_count"), counts.get("INCONCLUSIVE"), "INVALID_STATISTICAL_EVALUATION", "summary.evidence_quality.inconclusive_count");
        requireIntegerEqual(evidence == null ? null : evidence.get("cancelled_count"), counts.get("CANCELLED"), "INVALID_STATISTICAL_EVALUATION", "summary.evidence_quality.cancelled_count");
        if (evidence == null || !booleanValue(evidence.get("excluded_trials_remain_visible"), true)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation evidence boundary is malformed.");
        }

        JsonNode flaky = summary.get("flaky");
        String expectedFlaky = validAgentCount < requiredInteger(plan.get("minimum_valid_trial_count"), "INVALID_STATISTICAL_EVALUATION", "Sampling Plan minimum_valid_trial_count")
                ? "INSUFFICIENT_EVIDENCE"
                : (pass > 0 && fail > 0 ? "OBSERVED_FLAKY" : (pass == validAgentCount && validAgentCount > 0 ? "NO_FAILURE_OBSERVED" : (fail == validAgentCount && validAgentCount > 0 ? "CONSISTENT_FAILURE_OBSERVED" : "INSUFFICIENT_EVIDENCE")));
        if (flaky == null || !Objects.equals(text(flaky, "state"), expectedFlaky)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation flaky classification contradicts raw Trials.");
        }
        requireIntegerEqual(flaky.get("valid_trial_count"), validAgentCount, "INVALID_STATISTICAL_EVALUATION", "summary.flaky.valid_trial_count");

        JsonNode zero = summary.get("zero_tolerance");
        JsonNode zeroEvents = zero == null ? null : zero.get("events");
        int zeroCount = zeroEvents != null && zeroEvents.isArray() ? zeroEvents.size() : -1;
        requireIntegerEqual(zero == null ? null : zero.get("event_count"), zeroCount, "INVALID_STATISTICAL_EVALUATION", "summary.zero_tolerance.event_count");
        if (zeroCount < 0) invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation zero-tolerance events are malformed.");

        JsonNode families = summary.get("failure_families");
        if (families == null || !families.isArray()) invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation failure family distribution is malformed.");
        Map<String, Integer> familyCounts = new LinkedHashMap<>();
        for (JsonNode trial : evaluation.get("trials")) {
            if (!"AGENT_FAIL".equals(text(trial, "outcome"))) continue;
            JsonNode intelligence = trial.get("failure_intelligence");
            String family = text(intelligence, "cross_agent_family");
            if (family.isBlank()) family = text(intelligence, "domain_family");
            if (!family.isBlank()) familyCounts.put(family, familyCounts.getOrDefault(family, 0) + 1);
        }
        Set<String> summaryFamilies = new HashSet<>();
        for (JsonNode family : families) {
            String signature = text(family, "family_signature");
            if (signature.isBlank() || !summaryFamilies.add(signature)) invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation failure family identity is malformed.");
            int expectedFamilyCount = familyCounts.getOrDefault(signature, 0);
            requireIntegerEqual(family.get("fail_count"), expectedFamilyCount, "INVALID_STATISTICAL_EVALUATION", "failure_families.fail_count");
            requireIntegerEqual(family.get("denominator"), validAgentCount, "INVALID_STATISTICAL_EVALUATION", "failure_families.denominator");
            requireNumberEqual(family.get("failure_rate"), validAgentCount == 0 ? null : (double) expectedFamilyCount / validAgentCount, "INVALID_STATISTICAL_EVALUATION", "failure_families.failure_rate");
        }
        if (!summaryFamilies.equals(familyCounts.keySet())) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation failure family distribution contradicts raw Failure Intelligence.");
        }
        JsonNode historical = summary.get("historical_regression");
        if (historical == null || !booleanValue(historical.get("required"), true) || historical.get("passed") == null || !historical.get("passed").isBoolean()) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation historical regression boundary is malformed.");
        }
        JsonNode cost = summary.get("cost_token_latency");
        if (cost == null || !booleanValue(cost.get("unknown_values_are_not_zero"), true)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation unknown-value semantics are malformed.");
        }
        JsonNode adequacy = summary.get("adequacy");
        int minimum = requiredInteger(plan.get("minimum_valid_trial_count"), "INVALID_STATISTICAL_EVALUATION", "Sampling Plan minimum_valid_trial_count");
        requireIntegerEqual(adequacy == null ? null : adequacy.get("minimum_valid_trial_count"), minimum, "INVALID_STATISTICAL_EVALUATION", "summary.adequacy.minimum_valid_trial_count");
        if (adequacy == null
                || !booleanValue(adequacy.get("sample_target_reached"), attempted == requested)
                || !booleanValue(adequacy.get("minimum_valid_reached"), validAgentCount >= minimum)
                || !booleanValue(adequacy.get("evidence_sufficient"), validAgentCount >= minimum)) {
            invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Statistical Evaluation adequacy summary contradicts raw Trials.");
        }
    }

    private void validateStatisticalGateReferences(JsonNode artifact) {
        JsonNode gate = artifact == null ? null : artifact.get("statistical_gate");
        if (gate == null || !gate.isObject()) invalidStatistical("INVALID_STATISTICAL_GATE", "Statistical Gate is missing its gate object.");
        String status = text(gate, "status");
        if (!Set.of("COMPLETE", "INVALID").contains(status)) invalidStatistical("INVALID_STATISTICAL_GATE", "Statistical Gate status is not accepted.");
        if ("INVALID".equals(status)) {
            if (gate.get("validation_errors") == null || !gate.get("validation_errors").isArray() || gate.get("validation_errors").isEmpty()) {
                invalidStatistical("INVALID_STATISTICAL_GATE", "An INVALID Statistical Gate must retain validation errors.");
            }
            return;
        }
        JsonNode boundary = gate.get("authorization_boundary");
        if (!Boolean.FALSE.equals(boolOrNull(boundary, "release_executed"))
                || !Boolean.FALSE.equals(boolOrNull(boundary, "deployment_authorized"))) {
            invalidStatistical("INVALID_STATISTICAL_GATE", "Statistical Gate is not decision-only.");
        }
        JsonNode policy = canonicalArtifactFromRef(gate.get("policy_ref"), "STATISTICAL_POLICY", "Statistical Gate policy");
        JsonNode plan = canonicalArtifactFromRef(gate.get("sampling_plan_ref"), "STATISTICAL_SAMPLING_PLAN", "Statistical Gate sampling plan");
        JsonNode evaluation = canonicalArtifactFromRef(gate.get("evaluation_ref"), "STATISTICAL_EVALUATION", "Statistical Gate evaluation");
        validateStatisticalEvaluationArtifact(evaluation);
        validateStatisticalPolicyCompatibility(policy, plan, evaluation);
        String expected = expectedStatisticalDecisionStatus(policy, evaluation);
        if (!Objects.equals(expected, text(gate, "decision_status"))) {
            invalidStatistical("INVALID_STATISTICAL_GATE", "Statistical Gate decision status does not follow canonical Evaluation and Policy facts.");
        }
        JsonNode comparisonRef = gate.get("comparison_ref");
        if (comparisonRef != null && !comparisonRef.isNull()) canonicalArtifactFromRef(comparisonRef, "STATISTICAL_COMPARISON", "Statistical Gate comparison");
    }

    private void validateStatisticalPolicyCompatibility(JsonNode policyArtifact, JsonNode planArtifact, JsonNode evaluationArtifact) {
        JsonNode policy = policyArtifact == null ? null : policyArtifact.get("statistical_policy");
        JsonNode plan = planArtifact == null ? null : planArtifact.get("sampling_plan");
        JsonNode evaluation = evaluationArtifact == null ? null : evaluationArtifact.get("statistical_evaluation");
        if (policy == null || !policy.isObject() || plan == null || !plan.isObject() || evaluation == null || !evaluation.isObject()) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", "Statistical Policy, Plan, or Evaluation is malformed.");
        }
        JsonNode compatible = policy.get("compatible_sampling_plan");
        if (compatible == null || !compatible.isObject()
                || !Objects.equals(text(compatible, "suite_id"), text(plan.path("suite_ref"), "suite_id"))
                || !Objects.equals(text(compatible, "suite_version"), text(plan.path("suite_ref"), "suite_version"))) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", "Statistical Policy is incompatible with the canonical Sampling Plan.");
        }
        if (compatible.has("sampling_plan_version") && !Objects.equals(text(compatible, "sampling_plan_version"), text(plan, "sampling_plan_version"))) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", "Statistical Policy sampling plan version is incompatible.");
        }
        if (compatible.has("sampling_plan_id") && !Objects.equals(text(compatible, "sampling_plan_id"), text(plan, "sampling_plan_id"))) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", "Statistical Policy sampling plan id is incompatible.");
        }
        if (compatible.has("compatibility_key") && !Objects.equals(text(compatible, "compatibility_key"), text(plan, "compatibility_key"))) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", "Statistical Policy compatibility key is incompatible.");
        }
        if (compatible.has("agent") && !sameAgentBase(compatible.get("agent"), evaluation.get("agent"))) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", "Statistical Policy Agent identity is incompatible.");
        }
        if (compatible.has("scenario_ref") && !sameScenarioCore(compatible.get("scenario_ref"), evaluation.get("scenario_ref"))) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", "Statistical Policy Scenario identity is incompatible.");
        }
        JsonNode confidence = compatible.get("confidence");
        if (confidence != null && !confidence.isNull()
                && (!close(decimal(confidence.get("level")), decimal(plan.path("confidence").get("level")))
                || !Objects.equals(text(confidence, "method"), text(plan.path("confidence"), "method"))
                || !Objects.equals(text(confidence, "method_version"), text(plan.path("confidence"), "method_version")))) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", "Statistical Policy confidence contract is incompatible.");
        }
        String isolation = text(compatible, "trial_isolation");
        if (!isolation.isBlank() && !"fresh-per-trial".equals(isolation)) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", "Statistical Policy trial isolation is incompatible.");
        }
        JsonNode semantics = compatible.get("sample_semantics");
        if (semantics != null && (!"AGENT_PASS + AGENT_FAIL only".equals(text(semantics, "valid_agent_denominator"))
                || !"all attempted trials".equals(text(semantics, "evidence_denominator"))
                || !booleanValue(semantics.get("fresh_environment_per_trial"), true))) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", "Statistical Policy sample semantics are incompatible.");
        }
    }

    private String expectedStatisticalDecisionStatus(JsonNode policyArtifact, JsonNode evaluationArtifact) {
        JsonNode policy = policyArtifact.path("statistical_policy");
        JsonNode evaluation = evaluationArtifact.path("statistical_evaluation");
        JsonNode rules = policy.path("rules");
        JsonNode counts = evaluation.path("outcome_counts");
        int pass = requiredInteger(counts.get("AGENT_PASS"), "INVALID_STATISTICAL_REFERENCE", "AGENT_PASS");
        int fail = requiredInteger(counts.get("AGENT_FAIL"), "INVALID_STATISTICAL_REFERENCE", "AGENT_FAIL");
        int valid = pass + fail;
        int attempted = requiredInteger(evaluation.get("attempted_trial_count"), "INVALID_STATISTICAL_REFERENCE", "attempted_trial_count");
        int minimum = requiredInteger(rules.get("minimum_valid_trial_count"), "INVALID_STATISTICAL_REFERENCE", "minimum_valid_trial_count");
        int platform = requiredInteger(counts.get("PLATFORM_ERROR"), "INVALID_STATISTICAL_REFERENCE", "PLATFORM_ERROR")
                + requiredInteger(counts.get("ENVIRONMENT_ERROR"), "INVALID_STATISTICAL_REFERENCE", "ENVIRONMENT_ERROR");
        int zeroEvents = evaluation.path("summary").path("zero_tolerance").path("events").size();
        boolean historyPassed = Boolean.TRUE.equals(boolOrNull(evaluation.path("summary").path("historical_regression"), "passed"));
        Boolean historyRequired = boolOrNull(rules, "required_historical_regression_pass");
        if (zeroEvents > 0 || (Boolean.TRUE.equals(historyRequired) && !historyPassed)) return "BLOCKED";
        if (!"COMPLETE".equals(text(evaluation, "evaluation_status"))) return "INCONCLUSIVE";
        Double evidenceRate = attempted == 0 ? null : (double) (pass + fail) / attempted;
        Double platformRate = attempted == 0 ? null : (double) platform / attempted;
        Double minimumEvidenceRate = decimal(rules.get("minimum_evidence_valid_rate"));
        Double maximumPlatformRate = decimal(rules.get("maximum_platform_environment_error_rate"));
        if (valid < minimum || evidenceRate == null || minimumEvidenceRate == null || evidenceRate < minimumEvidenceRate
                || platformRate == null || maximumPlatformRate == null || platformRate > maximumPlatformRate) return "INCONCLUSIVE";
        Double successRate = (double) pass / valid;
        Double lower = decimal(evaluation.path("summary").path("agent_quality").path("confidence_interval").get("lower"));
        Double minimumSuccess = decimal(rules.get("minimum_agent_success_rate"));
        Double minimumLower = decimal(rules.get("minimum_confidence_lower_bound"));
        if (minimumSuccess == null || minimumLower == null || successRate < minimumSuccess || lower == null || lower < minimumLower) return "BLOCKED";
        String flaky = text(evaluation.path("summary").path("flaky"), "state");
        if ("OBSERVED_FLAKY".equals(flaky)) {
            String effect = text(rules, "observed_flaky_effect");
            if ("BLOCK".equals(effect) || "BLOCKED".equals(effect)) return "BLOCKED";
            if ("REVIEW".equals(effect) || "REVIEW_REQUIRED".equals(effect)) return "REVIEW_REQUIRED";
        }
        return "ELIGIBLE";
    }

    private JsonNode canonicalArtifactFromRef(JsonNode ref, String expectedType, String context) {
        if (ref == null || !ref.isObject()) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", context + " reference is malformed.");
        }
        String entityType = normalizeEntityType(text(ref, "entity_type"));
        String entityId = text(ref, "entity_id");
        if (entityType == null) {
            entityType = switch (text(ref, "kind")) {
                case "Statistical Policy" -> "STATISTICAL_POLICY";
                case "Statistical Sampling Plan" -> "STATISTICAL_SAMPLING_PLAN";
                case "Statistical Evaluation" -> "STATISTICAL_EVALUATION";
                case "Statistical Comparison" -> "STATISTICAL_COMPARISON";
                default -> null;
            };
            String idField = switch (entityType == null ? "" : entityType) {
                case "STATISTICAL_POLICY" -> "policy_id";
                case "STATISTICAL_SAMPLING_PLAN" -> "sampling_plan_id";
                case "STATISTICAL_EVALUATION" -> "evaluation_id";
                case "STATISTICAL_COMPARISON" -> "comparison_id";
                default -> "";
            };
            entityId = idField.isBlank() ? "" : text(ref, idField);
        }
        if (!expectedType.equals(entityType)) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", context + " reference has an incompatible entity type.");
        }
        if (entityId.isBlank()) invalidStatistical("INVALID_STATISTICAL_REFERENCE", context + " reference is missing an id.");
        return canonicalArtifact(entityType, entityId, context);
    }

    private JsonNode canonicalArtifact(String entityType, String entityId, String context) {
        try {
            ApiModels.ArtifactResponse response = readArtifact(entityType, entityId);
            if (response == null || response.artifactRef() == null || !response.artifactRef().resolved() || response.artifact() == null) {
                invalidStatistical("INVALID_STATISTICAL_REFERENCE", context + " does not resolve to a verified artifact.");
            }
            return response.artifact();
        } catch (EntityNotFoundException exception) {
            invalidStatistical("INVALID_STATISTICAL_REFERENCE", context + " is not registered in canonical metadata.");
            return null;
        }
    }

    private static boolean sameAgentBase(JsonNode left, JsonNode right) {
        if (left == null || right == null || !left.isObject() || !right.isObject()) return false;
        for (String field : List.of("agent_id", "agent_domain", "agent_type", "agent_contract_id", "agent_contract_version")) {
            if (text(left, field).isBlank() || !Objects.equals(text(left, field), text(right, field))) return false;
        }
        return !text(left, "agent_version").isBlank() && !text(left, "configuration_id").isBlank();
    }

    private static boolean sameScenarioCore(JsonNode left, JsonNode right) {
        return left != null && right != null && left.isObject() && right.isObject()
                && !text(left, "scenario_id").isBlank()
                && Objects.equals(text(left, "scenario_id"), text(right, "scenario_id"))
                && Objects.equals(text(left, "scenario_version"), text(right, "scenario_version"));
    }

    private static Integer integer(JsonNode node) {
        return node != null && node.isIntegralNumber() ? node.intValue() : null;
    }

    private static int requiredInteger(JsonNode node, String code, String field) {
        Integer value = integer(node);
        if (value == null) invalidStatistical(code, field + " must be an integer.");
        return value;
    }

    private static Double decimal(JsonNode node) {
        return node != null && node.isNumber() ? node.doubleValue() : null;
    }

    private static boolean booleanValue(JsonNode node, boolean expected) {
        return node != null && node.isBoolean() && node.booleanValue() == expected;
    }

    private static void requireIntegerEqual(JsonNode node, int expected, String code, String field) {
        if (integer(node) == null || integer(node) != expected) invalidStatistical(code, field + " contradicts canonical facts.");
    }

    private static void requireNumberEqual(JsonNode node, Double expected, String code, String field) {
        Double actual = decimal(node);
        if (expected == null) {
            if (node != null && !node.isNull()) invalidStatistical(code, field + " must be null when its denominator is empty.");
        } else if (actual == null || !close(actual, expected)) {
            invalidStatistical(code, field + " contradicts canonical facts.");
        }
    }

    private static boolean close(Double left, Double right) {
        return left == null ? right == null : right != null && Math.abs(left - right) <= 1.0e-6;
    }

    private static Double wilsonBound(int successes, int trials, double confidenceLevel, boolean upper) {
        if (trials == 0) return null;
        double z = 0.0;
        if (Math.abs(confidenceLevel - 0.90) <= 1.0e-9) z = 1.6448536269514722;
        else if (Math.abs(confidenceLevel - 0.95) <= 1.0e-9) z = 1.959963984540054;
        else if (Math.abs(confidenceLevel - 0.99) <= 1.0e-9) z = 2.5758293035489004;
        else invalidStatistical("INVALID_STATISTICAL_EVALUATION", "Unsupported confidence level for Wilson interval verification.");
        double proportion = (double) successes / trials;
        double denominator = 1.0 + (z * z / trials);
        double center = (proportion + (z * z / (2.0 * trials))) / denominator;
        double margin = (z / denominator) * Math.sqrt((proportion * (1.0 - proportion) / trials) + (z * z / (4.0 * trials * trials)));
        double value = upper ? Math.min(1.0, center + margin) : Math.max(0.0, center - margin);
        if (Math.abs(value) < 1.0e-15) value = 0.0;
        if (Math.abs(1.0 - value) < 1.0e-15) value = 1.0;
        return value;
    }

    private static void invalidStatistical(String code, String message) {
        throw new InvalidEvidenceException(code, message);
    }

    private void validateDecisionReferences(List<ApiModels.EntityRef> refs) {
        Map<String, ApiModels.EntityRef> byRole = new HashMap<>();
        for (ApiModels.EntityRef ref : refs) {
            if (ref != null && ref.role() != null) byRole.put(ref.role(), ref);
        }
        Map<String, String> required = Map.of(
                "policy_ref", "QUALITY_POLICY",
                "suite_ref", "EVALUATION_SUITE",
                "candidate_evaluation_ref", "EVALUATION",
                "comparison_ref", "COMPARISON",
                "gate_evaluation_ref", "QUALITY_GATE",
                "regression_ref", "REGRESSION"
        );
        for (Map.Entry<String, String> requiredRef : required.entrySet()) {
            ApiModels.EntityRef ref = byRole.get(requiredRef.getKey());
            if (ref == null || !requiredRef.getValue().equals(normalizeEntityType(ref.entityType())) || !has(ref.entityType(), ref.entityId())) {
                throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Release Decision references are incomplete or unavailable.");
            }
        }
        if (refs.size() < DECISION_ROLES.size()) {
            throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Release Decision references are incomplete.");
        }
    }

    private void validateStatisticalDecisionReferences(List<ApiModels.EntityRef> refs, JsonNode artifact) {
        Map<String, ApiModels.EntityRef> byRole = new HashMap<>();
        for (ApiModels.EntityRef ref : refs) {
            if (ref != null && ref.role() != null) byRole.put(ref.role(), ref);
        }
        Map<String, String> required = Map.of(
                "policy_ref", "STATISTICAL_POLICY",
                "sampling_plan_ref", "STATISTICAL_SAMPLING_PLAN",
                "evaluation_ref", "STATISTICAL_EVALUATION"
        );
        for (Map.Entry<String, String> requiredRef : required.entrySet()) {
            ApiModels.EntityRef ref = byRole.get(requiredRef.getKey());
            if (ref == null || !requiredRef.getValue().equals(normalizeEntityType(ref.entityType())) || !has(ref.entityType(), ref.entityId())) {
                throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Statistical Release Decision references are incomplete or unavailable.");
            }
        }
        if (refs.size() < STATISTICAL_DECISION_ROLES.size()) {
            throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Statistical Release Decision references are incomplete.");
        }
        ApiModels.EntityRef comparisonRef = byRole.get("comparison_ref");
        if (comparisonRef != null
                && (!"STATISTICAL_COMPARISON".equals(normalizeEntityType(comparisonRef.entityType()))
                || !has(comparisonRef.entityType(), comparisonRef.entityId()))) {
            throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Statistical Release Decision comparison reference is unavailable.");
        }
        JsonNode decision = artifact.path("statistical_release_decision");
        JsonNode evaluationSource = decision.get("evaluation_source_identity");
        if (evaluationSource != null) {
            ApiModels.EntityRef evaluationRef = byRole.get("evaluation_ref");
            MetadataRow evaluation = evaluationRef == null ? null : find("STATISTICAL_EVALUATION", evaluationRef.entityId());
            if (evaluation == null
                    || !Objects.equals(evaluation.sourceSha256(), text(evaluationSource, "source_sha256"))
                    || !Objects.equals(evaluation.runtimeVersion(), text(evaluationSource, "runtime_version"))) {
                throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Statistical Release Decision does not bind the canonical Evaluation source identity.");
            }
        }
        JsonNode policy = canonicalArtifact("STATISTICAL_POLICY", byRole.get("policy_ref").entityId(), "Statistical Release Decision policy");
        JsonNode plan = canonicalArtifact("STATISTICAL_SAMPLING_PLAN", byRole.get("sampling_plan_ref").entityId(), "Statistical Release Decision sampling plan");
        JsonNode evaluation = canonicalArtifact("STATISTICAL_EVALUATION", byRole.get("evaluation_ref").entityId(), "Statistical Release Decision evaluation");
        validateStatisticalEvaluationArtifact(evaluation);
        validateStatisticalPolicyCompatibility(policy, plan, evaluation);
        if (!Objects.equals(expectedStatisticalDecisionStatus(policy, evaluation), text(decision, "decision_status"))) {
            throw new InvalidEvidenceException("INVALID_DECISION_REFERENCE", "Statistical Release Decision status does not follow canonical Evaluation and Policy facts.");
        }
    }

    private void validateMetadataPayload(Map<String, Object> summary, List<ApiModels.EntityRef> refs) {
        try {
            String summaryJson = objectMapper.writeValueAsString(summary);
            String refsJson = objectMapper.writeValueAsString(refs);
            if (summaryJson.length() > 16_384 || refsJson.length() > 16_384) {
                throw new RequestValidationException("CANONICAL_METADATA_TOO_LARGE", "Canonical metadata must remain a bounded summary.");
            }
            String serialized = (summaryJson + refsJson).toLowerCase(Locale.ROOT);
            for (String forbidden : List.of("trajectory", "private_reasoning", "authorization", "bearer ", "password", "deepseek_api_key", "request_messages", "prompt")) {
                if (serialized.contains(forbidden)) {
                    throw new RequestValidationException("CANONICAL_METADATA_SECRET_OR_RAW", "Canonical metadata contains a forbidden raw or secret field.");
                }
            }
        } catch (JsonProcessingException exception) {
            throw new RequestValidationException("INVALID_METADATA_SUMMARY", "Canonical metadata summary is not serializable.");
        }
    }

    private ApiModels.MetadataView toView(MetadataRow row) {
        return toView(row, true);
    }

    private ApiModels.MetadataView toView(MetadataRow row, boolean verifyArtifact) {
        ApiModels.ArtifactSnapshot resolution;
        if (!verifyArtifact) {
            resolution = ApiModels.ArtifactSnapshot.registered(row.artifactRef(), row.entityType(), row.entityId());
        } else {
            try {
                resolution = artifactStore.verify(row.artifactRef(), row.entityType(), row.entityId());
            } catch (InvalidEvidenceException exception) {
                resolution = ApiModels.ArtifactSnapshot.unavailable(row.artifactRef(), exception.code(), row.entityType(), row.entityId());
            }
        }
        return new ApiModels.MetadataView(
                new ApiModels.MetadataRecord(
                        row.entityType(), row.entityId(), row.entitySchemaVersion(), row.artifactKind(), row.outcome(),
                        row.agentVersion(), row.evaluationId(), row.supersedesEntityId(), new ApiModels.SourceIdentity(row.sourceSha256(), row.runtimeVersion()),
                        row.keyRefs(), row.summary(), row.artifactRef(), row.registeredBy(), row.createdAt()
                ),
                resolution
        );
    }

    private static int boundedLimit(Integer requestedLimit) {
        if (requestedLimit == null || requestedLimit <= 0) return METADATA_DEFAULT_LIMIT;
        return Math.min(requestedLimit, METADATA_MAX_LIMIT);
    }

    private MetadataCursor decodeCursor(String encodedCursor) {
        if (encodedCursor == null || encodedCursor.isBlank()) return null;
        try {
            byte[] decoded = Base64.getUrlDecoder().decode(encodedCursor);
            JsonNode node = objectMapper.readTree(decoded);
            if (node == null || !node.isObject()
                    || !node.has("contract") || !node.has("version") || !node.has("entity_type")
                    || !node.has("ordering") || !node.has("limit") || !node.has("created_at")
                    || !node.has("entity_id")) {
                throw invalidCursor();
            }
            String entityType = node.get("entity_type").isNull() ? null : text(node, "entity_type");
            String ordering = text(node, "ordering");
            String createdAt = text(node, "created_at");
            String entityId = text(node, "entity_id");
            if (entityId.isBlank() || createdAt.isBlank() || ordering.isBlank() || !node.get("limit").canConvertToInt()) {
                throw invalidCursor();
            }
            return new MetadataCursor(
                    text(node, "contract"), node.get("version").asInt(), entityType, ordering,
                    node.get("limit").asInt(), createdAt, entityId
            );
        } catch (IllegalArgumentException | IOException exception) {
            throw invalidCursor();
        }
    }

    private void validateCursor(MetadataCursor cursor, String entityType, String ordering, int limit) {
        if (cursor == null) return;
        if (cursor.contract().isBlank() || cursor.version() <= 0) throw invalidCursor();
        if (!METADATA_CURSOR_CONTRACT.equals(cursor.contract()) || cursor.version() != 1
                || !Objects.equals(cursor.entityType(), entityType)
                || !Objects.equals(cursor.ordering(), ordering)
                || cursor.limit() != limit) {
            throw new RequestValidationException("INCOMPATIBLE_METADATA_CURSOR", "The metadata cursor does not match this entity type, ordering, or page size.");
        }
        cursorTimestamp(cursor);
    }

    private Timestamp cursorTimestamp(MetadataCursor cursor) {
        try {
            return Timestamp.from(Instant.parse(cursor.createdAt()));
        } catch (RuntimeException exception) {
            throw invalidCursor();
        }
    }

    private String encodeCursor(String entityType, String ordering, int limit, MetadataRow row) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("contract", METADATA_CURSOR_CONTRACT);
        node.put("version", 1);
        if (entityType == null) node.set("entity_type", NullNode.getInstance());
        else node.put("entity_type", entityType);
        node.put("ordering", ordering);
        node.put("limit", limit);
        node.put("created_at", row.createdAt());
        node.put("entity_id", row.entityId());
        try {
            return Base64.getUrlEncoder().withoutPadding().encodeToString(objectMapper.writeValueAsBytes(node));
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Metadata cursor could not be encoded.", exception);
        }
    }

    private static RequestValidationException invalidCursor() {
        return new RequestValidationException("INVALID_METADATA_CURSOR", "The metadata cursor is malformed or unsupported.");
    }

    private MetadataRow find(String entityType, String entityId) {
        if (entityType == null || entityId == null) return null;
        List<MetadataRow> rows = jdbcTemplate.query(
                "SELECT * FROM canonical_metadata WHERE entity_type = ? AND entity_id = ?",
                rowMapper(), entityType, entityId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    private MetadataRow findByIdempotency(String idempotencyKey) {
        List<MetadataRow> rows = jdbcTemplate.query(
                "SELECT * FROM canonical_metadata WHERE idempotency_key = ?",
                rowMapper(), idempotencyKey
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    private RowMapper<MetadataRow> rowMapper() {
        return (rs, rowNum) -> new MetadataRow(
                rs.getString("entity_type"), rs.getString("entity_id"), rs.getString("entity_schema_version"),
                rs.getString("artifact_kind"), rs.getString("outcome"), rs.getString("agent_version"),
                rs.getString("evaluation_id"), rs.getString("supersedes_entity_id"), rs.getString("source_sha256"), rs.getString("runtime_version"),
                readMap(rs.getString("summary_json")),
                readRefs(rs.getString("key_refs_json")),
                new ApiModels.ArtifactRef(
                        rs.getString("artifact_id"), rs.getString("artifact_key"), rs.getString("artifact_kind"),
                        rs.getString("artifact_schema_version"), rs.getString("artifact_content_sha256"),
                        rs.getString("artifact_source_sha256"), rs.getString("artifact_runtime_version")
                ),
                rs.getString("registered_by"), rs.getObject("created_at", java.time.OffsetDateTime.class).toInstant().toString()
        );
    }

    private static boolean sameFingerprint(MetadataRow existing, NormalizedManifest incoming) {
        ApiModels.ArtifactRef old = existing.artifactRef();
        ApiModels.ArtifactRef next = incoming.artifactRef();
        return old.artifactId().equals(next.artifactId())
                && old.artifactKind().equals(next.artifactKind())
                && old.schemaVersion().equals(next.schemaVersion())
                && old.contentSha256().equalsIgnoreCase(next.contentSha256())
                && old.sourceSha256().equalsIgnoreCase(next.sourceSha256())
                && old.runtimeVersion().equals(next.runtimeVersion());
    }

    private static String normalizeEntityType(String value) {
        if (value == null || value.isBlank()) return null;
        return value.trim().toUpperCase(Locale.ROOT);
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) throw new RequestValidationException("INVALID_MANIFEST", "Manifest is missing " + field + ".");
    }

    private static String json(Object value) {
        try {
            return new ObjectMapper().writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new RequestValidationException("INVALID_METADATA_SUMMARY", "Canonical metadata cannot be encoded.");
        }
    }

    private Map<String, Object> readMap(String value) {
        try {
            return objectMapper.readValue(value, new TypeReference<>() {});
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Stored canonical summary is invalid JSON.", exception);
        }
    }

    private List<ApiModels.EntityRef> readRefs(String value) {
        try {
            return objectMapper.readValue(value, new TypeReference<>() {});
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Stored canonical references are invalid JSON.", exception);
        }
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        return value != null && value.isTextual() ? value.asText() : "";
    }

    private static Boolean boolOrNull(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        return value != null && value.isBoolean() ? value.asBoolean() : null;
    }

    private static boolean isSha256(String value) {
        return value != null && value.matches("[0-9a-fA-F]{64}");
    }

    private record NormalizedManifest(
            String entityType,
            String entityId,
            String entitySchemaVersion,
            String outcome,
            String agentVersion,
            String evaluationId,
            String idempotencyKey,
            String supersedesEntityId,
            ApiModels.SourceIdentity sourceIdentity,
            List<ApiModels.EntityRef> keyRefs,
            Map<String, Object> summary,
            ApiModels.ArtifactRef artifactRef,
            String principalId
    ) {
    }

    private record MetadataRow(
            String entityType,
            String entityId,
            String entitySchemaVersion,
            String artifactKind,
            String outcome,
            String agentVersion,
            String evaluationId,
            String supersedesEntityId,
            String sourceSha256,
            String runtimeVersion,
            Map<String, Object> summary,
            List<ApiModels.EntityRef> keyRefs,
            ApiModels.ArtifactRef artifactRef,
            String registeredBy,
            String createdAt
    ) {
    }

    private record MetadataCursor(
            String contract,
            int version,
            String entityType,
            String ordering,
            int limit,
            String createdAt,
            String entityId
    ) {
    }
}
