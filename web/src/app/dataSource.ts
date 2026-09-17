import { controlPlaneDataSourceMode } from "../data/controlPlaneApi";

export const DATA_SOURCE_MODE = controlPlaneDataSourceMode();
export const DATA_SOURCE_LABEL = DATA_SOURCE_MODE === "api" ? "Control Plane API" : "reviewed fixture corpus";
export const DATA_SOURCE_FOOTNOTE = DATA_SOURCE_MODE === "api" ? "Control Plane API + verified immutable artifact" : "reviewed fixture artifact";
