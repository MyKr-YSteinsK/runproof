import { describe, expect, it, vi, afterEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nProvider } from "../../i18n";
import { LabPage } from "./LabPage";
import { labCopy } from "./copy";
import { capabilities, getSession, parseSession, startSession, witnessBytes } from "./labApi";

const sid = "session-" + "a".repeat(32);
const base = () => ({ schema_version: "rpf-lab-v1", session_id: sid, domain: "order", run_id: "rpf45-test",
  source: "LIVE_LOCAL_SIMULATION", status: "RUNNING", contracts: {}, events: [], result: null, witness: null });
afterEach(() => vi.unstubAllGlobals());
describe("isolated API Lab", () => {
  it("rejects wrong schema, source, identity and unsupported success", () => {
    expect(parseSession(base(), sid).status).toBe("RUNNING");
    for (const changed of [{schema_version:"old"}, {source:"REVIEWED"}, {session_id:"path/../"},
      {status:"SUCCESS"}, {status:"COMPLETED"}, {result:{}}, {events:[{seq:9}]}]) {
      expect(() => parseSession({...base(), ...changed})).toThrow();
    }
    expect(() => parseSession(base(), "session-wrong")).toThrow();
  });
  it("sends only allowlisted setup; retries retain supplied idempotency key and no bearer", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(base()), { headers: {"Content-Type":"application/json"} })));
    vi.stubGlobal("fetch", fetchMock);
    await startSession("order", "same-request-key"); await startSession("order", "same-request-key");
    const first = fetchMock.mock.calls[0];
    expect(first[0]).toBe("/effectwitness-api/sessions");
    expect(JSON.parse(first[1].body)).toEqual({domain:"order", mode:"LOCAL_CONTROLLED_CAPTURE", request_id:"same-request-key"});
    expect(first[1].headers).toEqual({"Content-Type":"application/json"});
    expect(fetchMock.mock.calls[1][1].body).toBe(first[1].body);
  });
  it("fails closed on gateway outage, HTML fallback, malformed capability and missing sessions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    await expect(capabilities()).rejects.toThrow("GATEWAY_UNAVAILABLE");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>sample</html>")));
    await expect(capabilities()).rejects.toThrow("GATEWAY_UNAVAILABLE");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", {headers:{"Content-Type":"application/json"}})));
    await expect(capabilities()).rejects.toThrow("INVALID_CAPABILITY_DTO");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('{"error_code":"SESSION_NOT_FOUND"}', {status:404,headers:{"Content-Type":"application/json"}})));
    await expect(getSession(sid)).rejects.toThrow("SESSION_NOT_FOUND");
  });
  it("does not download before valid verified completion", async () => {
    const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
    await expect(witnessBytes(parseSession(base()))).rejects.toThrow("NO_VALID_WITNESS");
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("rejects downloaded bytes that disagree with the session hash", async () => {
    const c = {experiment:{run_id:"rpf45-test",domain:"order"}};
    const complete = {...base(),status:"COMPLETED",contracts:c,
      witness:{status:"CONTENT_CHECKED_LOCAL",external_anchor:false,issuer_authenticity:"NOT_ESTABLISHED",sha256:"0".repeat(64),bytes:3},
      result:{schema_version:"rpf-effect-witness-v2",domain:"order",contracts:c,
        claims:{contract_outcome:"CONTRACT_SATISFIED_IN_RUN",fault_activation:"TRIGGERED",attribution_strength:"CORRELATIONAL_ONLY",reproduction:"NOT_TESTED"},
        observation:{effect:{},fault:{},feedback:{},authority_before:{data:{}},authority_after:{data:{}},tool_calls:[],cleanup:{},reconciliation:{}}}};
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response("{}\n")));
    await expect(witnessBytes(parseSession(complete))).rejects.toThrow("WITNESS_HASH_MISMATCH");
  });
  it("uses an independent Lab shell and bilingual complete copy without a success fixture", () => {
    const html = renderToStaticMarkup(<I18nProvider><LabPage path="/effectwitness" search="" /></I18nProvider>);
    expect(html).toContain("LOCAL SIMULATION GATEWAY");
    expect(html).toContain("/runs"); expect(html).toContain("/executions");
    expect(html).not.toContain("TRUSTED_EXTERNAL_ANCHOR");
    expect(html).toContain("UNAVAILABLE");
    expect(Object.keys(labCopy["en-US"])).toEqual(Object.keys(labCopy["zh-CN"]));
    expect(renderToStaticMarkup(<I18nProvider><LabPage path="/effectwitness/invalid" search="" /></I18nProvider>)).toContain("INVALID_LAB_ROUTE");
  });
});
