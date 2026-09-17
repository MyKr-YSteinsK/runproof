export type StatusTone = "success" | "fault" | "error" | "neutral" | "review";

export const StatusTag = ({ status, tone = "neutral" }: { status: string; tone?: StatusTone }) => (
  <span className={`status-tag ${tone}`}><i aria-hidden="true" />{status}</span>
);
