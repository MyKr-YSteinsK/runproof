import { afterEach, describe, expect, it, vi } from "vitest";
import type { Plugin, ViteDevServer, UserConfig } from "vite";

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });
type Request = { url: string; method: string; headers: Record<string, string> };
type Response = { statusCode: number; setHeader: (name: string, value: string) => void; end: (body: string) => void };
type Middleware = (request: Request, response: Response, next: () => void) => void;
function middleware(config: UserConfig) {
  const boundary = config.plugins?.flat().find(p => p && typeof p === "object" && "name" in p && p.name === "local-lab-boundary") as Plugin;
  let handler: Middleware | undefined;
  const server = { middlewares: { use: (value: Middleware) => { handler = value; } } };
  (boundary.configureServer as (server: ViteDevServer) => void)(server as unknown as ViteDevServer);
  return (request: Request) => {
    const result = {statusCode:200,body:"",next:false};
    const response: Response = { statusCode:200,setHeader:()=>{},end:(body)=>{result.body=body;} };
    handler!(request,response,()=>{result.next=true;}); result.statusCode=response.statusCode;
    return result;
  };
}
describe("server-only local Lab proxy", () => {
  it("is disabled by default and preserves old read-only proxy", async () => {
    vi.stubEnv("RPF_EW_LAB_ENABLED","0"); vi.stubEnv("RPF_EW_LAB_GATEWAY_TOKEN","");
    const config=(await import("../../../../vite.config")).default;
    expect(config.server?.port).toBe(4173);
    expect(config.server?.proxy?.["/effectwitness-api"]).toBeUndefined();
    expect(config.server?.proxy?.["/api"]).toBeDefined();
    const result=middleware(config)({url:"/effectwitness-api/capabilities",method:"GET",headers:{host:"127.0.0.1:4185"}});
    expect(result.statusCode).toBe(503); expect(result.body).toContain("LAB_DISABLED"); expect(result.next).toBe(false);
  });
  it("isolates explicit enablement and rejects cross-site/missing-origin writes before proxying", async () => {
    vi.stubEnv("RPF_EW_LAB_ENABLED","1"); vi.stubEnv("RPF_EW_LAB_GATEWAY_TOKEN","test-server-only-"+"x".repeat(32));
    const config=(await import("../../../../vite.config")).default;
    expect(config.server?.port).toBe(4185); expect(config.server?.host).toBe("127.0.0.1");
    expect(config.server?.proxy?.["/api"]).toBeDefined();
    expect(config.server?.proxy?.["/effectwitness-api"]).toBeDefined();
    const invoke=middleware(config);
    expect(invoke({url:"/effectwitness-api/sessions",method:"POST",headers:{host:"127.0.0.1:4185"}}).statusCode).toBe(403);
    expect(invoke({url:"/effectwitness-api/sessions",method:"POST",headers:{host:"127.0.0.1:4185",origin:"https://evil.invalid"}}).statusCode).toBe(403);
    expect(invoke({url:"/effectwitness-api/sessions",method:"POST",headers:{host:"evil.invalid",origin:"http://127.0.0.1:4185"}}).statusCode).toBe(403);
    expect(invoke({url:"/effectwitness-api/sessions",method:"POST",headers:{host:"127.0.0.1:4185",origin:"http://127.0.0.1:4185"}}).next).toBe(true);
    expect(invoke({url:"/api/v1/runs",method:"GET",headers:{}}).next).toBe(true);
  });
});
