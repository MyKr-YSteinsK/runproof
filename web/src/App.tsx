import { lazy, Suspense, useEffect, useState } from "react";
import { readLocation } from "./app/navigation";
import { useI18n } from "./i18n";

const CanonicalApp = lazy(() => import("./CanonicalApp"));
const AgentPage = lazy(() => import("./features/effectwitness/CompetitionAgentPage").then(m => ({default: m.CompetitionAgentPage})));
const ProductPage = lazy(() => import("./features/effectwitness/ProductLocalPage").then(m => ({default: m.ProductLocalPage})));

export default function App() {
  const [location, setLocation] = useState(readLocation);
  const zh = useI18n().locale === "zh-CN";
  useEffect(() => {
    const update = () => setLocation(readLocation());
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  const local = import.meta.env.VITE_RPF_RECORDED_DELIVERY !== "1";
  const page = local && location.pathname === "/effectwitness/agent" ? <AgentPage search={location.search} />
    : local && location.pathname === "/effectwitness/live-local" ? <ProductPage search={location.search} />
    : <CanonicalApp />;
  return <Suspense fallback={<p role="status">{zh ? "正在加载页面" : "Loading page"}</p>}>{page}</Suspense>;
}
