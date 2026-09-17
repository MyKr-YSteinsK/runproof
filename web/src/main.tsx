import { Component, StrictMode, useEffect, useRef, type ErrorInfo, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/index.css";
import { I18nProvider, useI18n } from "./i18n";
import { localizeLegacyText } from "./i18n/legacyCopy";
import { LocaleSwitcher } from "./components/LocaleSwitcher";

function RenderErrorFallback({ error }: { error: Error }) {
  const { t } = useI18n();
  return <main className="data-source-state" aria-live="polite"><div className="data-source-state-card error"><LocaleSwitcher /><span className="eyebrow">CONTROL PLANE UI · RPF-19</span><h1>{t("app.renderError.title")}</h1><p>{t("app.renderError.description")}</p><code>{error.message}</code></div></main>;
}

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
      return <RenderErrorFallback error={this.state.error} />;
    }
    return this.props.children;
  }
}

function LegacyCopyBridge() {
  const { locale } = useI18n();
  const originals = useRef(new WeakMap<Text, string>());
  useEffect(() => {
    const root = document.getElementById("root");
    if (!root) return;
    // React may reuse text nodes when the locale changes. Reset the source
    // snapshot after that render so a previous translated value can never
    // overwrite the new locale on the next observer pass.
    originals.current = new WeakMap<Text, string>();
    const translate = (node: Node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node as Text;
        const parent = text.parentElement;
        if (!parent || parent.closest("pre, code, .mono, .status-tag")) return;
        const source = originals.current.get(text) ?? text.data;
        originals.current.set(text, source);
        const next = localizeLegacyText(locale, source);
        if (text.data !== next) text.data = next;
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      const element = node as Element;
      for (const attribute of ["aria-label", "title"]) {
        const value = element.getAttribute(attribute);
        if (value) {
          const next = localizeLegacyText(locale, value);
          if (value !== next) element.setAttribute(attribute, next);
        }
      }
      node.childNodes.forEach(translate);
    };
    translate(root);
    const observer = new MutationObserver((records) => records.forEach((record) => record.addedNodes.forEach(translate)));
    observer.observe(root, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [locale]);
  return null;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider><AppErrorBoundary><LegacyCopyBridge /><App /></AppErrorBoundary></I18nProvider>
  </StrictMode>,
);
