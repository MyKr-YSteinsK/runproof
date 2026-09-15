import profile from "../../../demo/rpf-19-golden-demo-v1.json";

export interface GoldenDemoArtifactRef {
  role: string;
  path: string;
  artifact_kind: string;
  schema_version: string;
  entity_type: string;
  entity_id: string;
  content_sha256: string;
  source_sha256: string;
}

export interface GoldenDemoProfile {
  schema_version: string;
  demo: {
    demo_id: string;
    version: string;
    title: string;
    source_commit: string;
    runtime_source_sha256: string;
    seed_command: string;
    start_command: string;
    load_method: string;
    no_provider_required: boolean;
    no_cloud_required: boolean;
    no_release_or_deploy: boolean;
  };
  agents: Array<{ agent_id: string; domain: string; role: string; evidence_role: string }>;
  selected: {
    baseline_evaluation: string;
    candidate_evaluation: string;
    deterministic_evaluation: string;
    statistical_evaluations: string[];
    statistical_comparison: string;
    flagship_failure_case: string;
    flagship_failure_cluster: string;
    cross_agent_failure_cluster: string;
    version_bisect: string;
    release_decision: string;
    unknown_outcome_run: string;
  };
  expected_assertions: string[];
  reviewed_artifacts: GoldenDemoArtifactRef[];
}

export const goldenDemoProfile = profile as GoldenDemoProfile;

export const goldenDemoArtifact = (role: string): GoldenDemoArtifactRef => {
  const artifact = goldenDemoProfile.reviewed_artifacts.find((item) => item.role === role);
  if (!artifact) throw new Error(`Golden Demo artifact role is missing: ${role}`);
  return artifact;
};

export const goldenDemoRefId = (role: string): string => goldenDemoArtifact(role).entity_id;
