import { describe, it, expect, vi, afterEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nProvider } from "../../i18n";
import { LivePage, liveText } from "./LivePage";
import { parseLive, startLive, getLive, liveCapabilities, liveWitness, type LiveTrial } from "./liveApi";

const sid="exploration-"+"a".repeat(32), sha="b".repeat(64);
const base=()=>({schema_version:"rpf-lab-exploration-v1",session_id:sid,request_id:"same-request",status:"RUNNING",
  run_outcome:"INCONCLUSIVE",source:"LIVE_LOCAL_SIMULATION",explorer:"LIVE_EXPLORER_DEEPSEEK",target_driver:"DETERMINISTIC_CONTROLLED_TARGET",
  rationale:"RATIONALE_NOT_RECORDED",plan_digest:sha,plan:{session_id:sid},selections:[],trials:[],events:[],usage:{},provider_requests:[],research:{L1:false,L2:false,H1:"NOT_PROVEN_IN_THIS_RUN"}});
afterEach(()=>vi.unstubAllGlobals());
describe("paid order PGE boundary",()=>{
  it("rejects fabricated completion, historical provenance, wrong identity and malformed wrapper",()=>{
    expect(parseLive(base(),sid).status).toBe("RUNNING");
    for(const change of [{status:"COMPLETED"},{source:"RESEARCH_RPF42_REPORTED"},{explorer:"MOCK"},{target_driver:"LLM"},{rationale:"invented reason"},
      {session_id:"../ledger.json"},{plan_digest:"wrong"},{plan:{session_id:"other"}},{trials:[{}]},{events:[{seq:3}]}])
      expect(()=>parseLive({...base(),...change},sid)).toThrow();
    expect(()=>parseLive(base(),"other")).toThrow();
  });
  it("new exact endpoint retains idempotency and never sends bearer or candidate",async()=>{
    const fetchMock=vi.fn().mockImplementation(()=>Promise.resolve(new Response(JSON.stringify(base()),{headers:{"Content-Type":"application/json"}})));
    vi.stubGlobal("fetch",fetchMock);
    await startLive("same-request");await startLive("same-request");
    const [url,init]=fetchMock.mock.calls[0];
    expect(url).toBe("/effectwitness-api/explorations");
    expect(JSON.parse(init.body)).toEqual({domain:"order",mode:"PGE_LIVE_ORDER",request_id:"same-request"});
    expect(init.headers).toEqual({"Content-Type":"application/json"});
    expect(fetchMock.mock.calls[1][1].body).toBe(init.body);
    await getLive(sid);expect(fetchMock.mock.calls[2][0]).toBe("/effectwitness-api/explorations/"+sid);
  });
  it("capability comes from backend; missing key, disabled and outage remain distinct",async()=>{
    for(const explorer of ["DISABLED","KEY_MISSING","AVAILABLE","UNAVAILABLE"]){
      vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify({schema_version:"rpf-lab-exploration-v1",explorer,enabled:explorer==="AVAILABLE",busy:false,remaining_sessions:1,limits:{}}),{headers:{"Content-Type":"application/json"}})));
      expect((await liveCapabilities()).explorer).toBe(explorer);
    }
    vi.stubGlobal("fetch",vi.fn().mockRejectedValue(new Error("offline")));
    await expect(liveCapabilities()).rejects.toThrow("GATEWAY_UNAVAILABLE");
    await expect(getLive(sid)).rejects.toThrow("GATEWAY_UNAVAILABLE");
  });
  it("ineligible profiles cannot request a certificate",async()=>{
    const f=vi.fn();vi.stubGlobal("fetch",f);
    const t={witness:{status:"NOT_ISSUED_PROFILE_NOT_ELIGIBLE"}} as LiveTrial;
    await expect(liveWitness(parseLive(base()),t)).rejects.toThrow("WITNESS_NOT_ISSUED");expect(f).not.toHaveBeenCalled();
  });
  it("eligible bytes fail closed on corrupted hash and gateway outage",async()=>{
    const t={round:1,witness:{status:"CONTENT_CHECKED_LOCAL",sha256:sha,bytes:2}} as LiveTrial;
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response("{}")));
    await expect(liveWitness(parseLive(base()),t)).rejects.toThrow("WITNESS_HASH_MISMATCH");
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response("{}",{status:503})));
    await expect(liveWitness(parseLive(base()),t)).rejects.toThrow("WITNESS_UNAVAILABLE");
  });
  it("setup makes paid mode explicit and remains disabled without live capabilities",()=>{
    const html=renderToStaticMarkup(<I18nProvider><LivePage path="/effectwitness/explorations" search=""/></I18nProvider>);
    expect(html).toContain("disabled");expect(html).toContain("UNAVAILABLE");expect(html).toContain("12,000");
    expect(html).toContain("/effectwitness");
    expect(liveText["en-US"].title).toContain("Live Explorer");expect(liveText["zh-CN"].title).toContain("实时");
    for(const locale of ["en-US","zh-CN"] as const){expect(liveText[locale].note).toContain("¥1.50");expect(liveText[locale].local).toContain("CONTENT_CHECKED_LOCAL");}
  });
});
