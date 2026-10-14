import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./worker.mjs";

const unsafe = { JAZN_PRIVATE_MCP: { fetch() { throw Error("private MCP was reached without OAuth"); } } };
async function invoke(path, method="GET") {
  return worker.fetch(new Request("https://jazn-runtime.example.workers.dev"+path,{method}), unsafe);
}
test("health reports staging gateway, not authenticated runtime",async()=>{
  const r=await invoke("/healthz");
  assert.equal(r.status,200);
  const value=await r.json();
  assert.equal(value.mcp_available,false);
  assert.equal(r.headers.get("cache-control"),"no-store");
});
test("MCP GET and POST are denied without OAuth, without VPC access",async()=>{
  for(const method of ["GET","POST"]){
    const r=await invoke("/mcp",method);
    assert.equal(r.status,503);
    const body=await r.json();
    assert.equal(body.must_not_resubmit_user_message,true);
  }
});
test("OAuth discovery paths cannot impersonate an authorization server",async()=>{
  for(const path of ["/.well-known/oauth-protected-resource","/.well-known/oauth-authorization-server"]){
    const r=await invoke(path);
    assert.equal(r.status,503);
    assert.equal((await r.json()).reason,"oauth_configuration_required");
  }
});
test("all unregistered paths stay closed",async()=>{
  const r=await invoke("/private-memory");
  assert.equal(r.status,404);
});
