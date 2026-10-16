import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./worker.mjs";

const PUBLIC="https://jazn-runtime.example.workers.dev",ISSUER="https://accounts.example.test",RESOURCE=PUBLIC+"/mcp";
const SCOPES=["jazn:mcp:connect"];
const unsafe={JAZN_PRIVATE_MCP:{fetch(){throw Error("MCP reached without OAuth");}}};
const reply=(data,status=200,headers={})=>new Response(JSON.stringify(data),{status,headers:{"content-type":"application/json",...headers}});
function enabled(fetch){return {JAZN_INGRESS_MODE:"verified_oauth_proxy",JAZN_PUBLIC_MCP_URL:RESOURCE,JAZN_OAUTH_ISSUER_URL:ISSUER,JAZN_PRIVATE_MCP:{fetch}};}
function backend(bad={}){
  const calls=[];
  async function fetch(url,init){
    const path=new URL(url).pathname,headers=new Headers(init.headers);calls.push({path,method:init.method,headers});
    if(path==="/.well-known/oauth-protected-resource")
      return reply({resource:bad.resource?PUBLIC+"/wrong":RESOURCE,
        authorization_servers:[bad.issuer?"https://wrong.example":ISSUER],
        scopes_supported:bad.scope?SCOPES.slice(0,1):SCOPES});
    if(path==="/mcp"&&init.method==="GET"&&!headers.has("authorization"))
      return reply({},bad.challenge?200:401,{"www-authenticate":'Bearer resource_metadata="'+PUBLIC+'/.well-known/oauth-protected-resource"'});
    if(bad.redirect)return reply({},302,{location:"https://evil.example"});
    return reply({result:{ok:true}},200,{"set-cookie":"secret=1"});
  }
  return {fetch,calls};
}
function invoke(path,env=unsafe,method="GET",headers={},body){
  return worker.fetch(new Request(PUBLIC+path,{method,headers,body}),env);
}
test("staging is fail-closed and cannot access VPC",async()=>{
  const h=await invoke("/healthz");assert.equal(h.status,200);
  assert.equal((await h.json()).mcp_available,false);
  for(const method of ["GET","POST"]){const r=await invoke("/mcp",unsafe,method);assert.equal(r.status,503);
    assert.equal((await r.json()).must_not_resubmit_user_message,true);}
  for(const path of ["/.well-known/oauth-protected-resource","/.well-known/oauth-authorization-server"])
    assert.equal((await invoke(path)).status,503);
  assert.equal((await invoke("/private-memory")).status,404);
});
test("a flag or a bearer alone never enables a false OAuth server",async()=>{
  assert.equal((await invoke("/mcp",{JAZN_INGRESS_MODE:"verified_oauth_proxy",JAZN_PUBLIC_MCP_URL:RESOURCE,JAZN_OAUTH_ISSUER_URL:ISSUER})).status,503);
  for(const bad of [{resource:true},{issuer:true},{scope:true},{challenge:true}]){
    const b=backend(bad);const r=await invoke("/mcp",enabled(b.fetch),"POST",{authorization:"Bearer arbitrary"},"{}");
    assert.equal(r.status,503);assert.equal(b.calls.filter(c=>c.headers.has("authorization")).length,0);
  }
});
test("proxy preserves MCP authorization and protocol only after OAuth probe",async()=>{
  const b=backend();const r=await invoke("/mcp",enabled(b.fetch),"POST",
    {authorization:"Bearer opaque","content-type":"application/json","mcp-protocol-version":"2026-07-28",cookie:"do-not-forward=1","x-forwarded-for":"1.2.3.4"},"{}");
  assert.equal(r.status,200);assert.equal((await r.json()).result.ok,true);
  assert.equal(r.headers.get("set-cookie"),null);assert.equal(r.headers.get("cache-control"),"no-store");
  assert.equal(b.calls.length,3);
  const h=b.calls[2].headers;assert.equal(h.get("authorization"),"Bearer opaque");
  assert.equal(h.get("mcp-protocol-version"),"2026-07-28");
  assert.equal(h.get("cookie"),null);assert.equal(h.get("x-forwarded-for"),null);
});
test("metadata is proxied only after OAuth challenge",async()=>{
  const b=backend();const r=await invoke("/.well-known/oauth-protected-resource",enabled(b.fetch));
  assert.equal(r.status,200);assert.equal((await r.json()).resource,RESOURCE);
  assert.equal(b.calls.length,3);
});
test("unregistered methods, query tokens, redirects, bad host and VPC failures fail closed",async()=>{
  const b=backend({redirect:true}),env=enabled(b.fetch);
  assert.equal((await invoke("/mcp",env,"PUT")).status,405);
  assert.equal((await invoke("/mcp?access_token=a",env)).status,405);
  assert.equal((await invoke("/.well-known/oauth-authorization-server",env)).status,405);
  assert.equal(b.calls.length,0);
  const r=await invoke("/mcp",env,"POST",{authorization:"Bearer token"},"{}");
  assert.equal(r.status,503);assert.equal(r.headers.get("location"),null);
  const wrong=enabled(backend().fetch);wrong.JAZN_PUBLIC_MCP_URL="http://jazn-runtime.example.workers.dev/mcp";
  assert.equal((await invoke("/mcp",wrong)).status,503);
  assert.equal((await invoke("/mcp",enabled(()=>{throw Error("network down");}))).status,503);
});
