import {
  getControlPlaneSnapshot,
  type ControlPlaneCorpusSnapshot,
} from "./artifacts";
import {
  getStatisticalSnapshot,
  type StatisticalCorpusSnapshot,
} from "./statistical";

export type CanonicalDataSource = "api" | "fixture";

export interface CanonicalSnapshot {
  source: CanonicalDataSource;
  revision: number;
  artifacts: ControlPlaneCorpusSnapshot;
  statistical: StatisticalCorpusSnapshot;
}

export const createCanonicalSnapshot = (
  source: CanonicalDataSource,
  revision = 0,
): CanonicalSnapshot => ({
  source,
  revision,
  artifacts: getControlPlaneSnapshot(),
  statistical: getStatisticalSnapshot(),
});
