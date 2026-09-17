import { Component, StrictMode, type ErrorInfo, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/index.css";

class AppErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("RunProof UI render failed", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return <main className="data-source-state" aria-live="polite"><div className="data-source-state-card error"><span className="eyebrow">CONTROL PLANE UI · RPF-19</span><h1>Overview could not be rendered.</h1><p>The page stopped instead of presenting a partial or unverified evidence view.</p><code>{this.state.error.message}</code></div></main>;
    }
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppErrorBoundary><App /></AppErrorBoundary>
  </StrictMode>,
);
