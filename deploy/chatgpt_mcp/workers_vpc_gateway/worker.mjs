// Jaźń Workers VPC: staging by default. No anonymous MCP forwarding.
// The private MCP resource server owns OAuth token, audience and scope checks.
// The edge requires public resource metadata and a genuine 401 challenge first.
const COMMON={"content-type":"application/json; charset=utf-8","cache-control":"no-store","x-content-type-options":"nosniff"};
const SCOPES=["jazn:mcp:connect"];
const COPY=new Set(["authorization","accept","content-type","mcp-protocol-version","mcp-session-id","last-event-id","mcp-method","mcp-name","idempotency-key"]);
function json(value,status=200,more={}){return new Response(JSON.stringify(value),{status,headers:{...COMMON,...more}});}
function unavailable(reason){return json({error:"mcp_unavailable",reason,must_not_resubmit_user_message:true},503,{"retry-after":"60"});}
function configuration(env,requestUrl){
  if(env?.JAZN_INGRESS_MODE!=="verified_oauth_proxy")return null;
  try{
    const resource=new URL(env.JAZN_PUBLIC_MCP_URL),issuer=new URL(env.JAZN_OAUTH_ISSUER_URL);
    if(resource.protocol!=="https:"||resource.pathname!=="/mcp"||resource.search||resource.hash||resource.username||resource.password||
      issuer.protocol!=="https:"||issuer.search||issuer.hash||issuer.username||issuer.password||
      requestUrl.origin!==resource.origin||typeof env.JAZN_PRIVATE_MCP?.fetch!=="function")return null;
    return {resource:resource.href,issuer:issuer.href.replace(/\/$/,""),origin:resource.origin};
  }catch{return null;}
}
function privateUrl(config,path){
  const u=new URL(config.origin);u.protocol="http:";u.pathname=path;
  // VPC Service fixes the actual private host/port independent of URL host.
  return u.href;
}
function vpcFetch(env,url,init){return env.JAZN_PRIVATE_MCP.fetch(url,{...init,redirect:"manual"});}
async function validatePrivateOAuth(env,config){
  try{
    const d=await vpcFetch(env,privateUrl(config,"/.well-known/oauth-protected-resource"),
      {method:"GET",headers:{accept:"application/json"}});
    if(d.status!==200)return false;
    const raw=await d.text();if(raw.length>65536)return false;
    const m=JSON.parse(raw);
    if(m?.resource!==config.resource||!Array.isArray(m.authorization_servers)||
      !m.authorization_servers.includes(config.issuer)||!Array.isArray(m.scopes_supported)||
      !SCOPES.every(s=>m.scopes_supported.includes(s)))return false;
    const challenge=await vpcFetch(env,privateUrl(config,"/mcp"),
      {method:"GET",headers:{accept:"text/event-stream, application/json"}});
    const auth=challenge.headers.get("www-authenticate")||"";
    return challenge.status===401&&/^\s*Bearer\b/i.test(auth)&&
      auth.includes('resource_metadata="'+config.origin+'/.well-known/oauth-protected-resource"');
  }catch{return false;}
}
function allowed(url,method){
  if(url.search||url.hash)return false;
  if(url.pathname==="/mcp")return ["GET","POST","DELETE"].includes(method);
  return url.pathname==="/.well-known/oauth-protected-resource"&&method==="GET";
}
function safeHeaders(request){
  const headers=new Headers();
  for(const [k,v] of request.headers.entries())if(COPY.has(k)||k.startsWith("x-mcp-"))headers.set(k,v);
  return headers;
}
export default{
  async fetch(request,env){
    const url=new URL(request.url);
    if(request.method==="GET"&&url.pathname==="/healthz")
      return json({gateway:"jazn-runtime",route:"cloudflare-workers-vpc",transport:"https",
        mcp_available:false,reason:"healthz_is_not_authenticated_runtime_readiness"});
    if(url.pathname!=="/mcp"&&!url.pathname.startsWith("/.well-known/"))return json({error:"not_found"},404);
    const cfg=configuration(env,url);
    if(!cfg)return unavailable("oauth_configuration_required");
    if(!allowed(url,request.method))return json({error:"method_or_path_not_allowed"},405);
    // Never trust a bearer string, stale status or a binding alone.
    if(!await validatePrivateOAuth(env,cfg))return unavailable("private_oauth_boundary_not_verified");
    try{
      const opts={method:request.method,headers:safeHeaders(request)};
      if(request.method==="POST")opts.body=request.body;
      const r=await vpcFetch(env,privateUrl(cfg,url.pathname),opts);
      if(r.status>=300&&r.status<400)return unavailable("upstream_redirect_refused");
      const headers=new Headers(r.headers);
      for(const k of ["set-cookie","location","server","connection","transfer-encoding"])headers.delete(k);
      headers.set("cache-control","no-store");headers.set("x-content-type-options","nosniff");
      return new Response([204,304].includes(r.status)?null:r.body,{status:r.status,headers});
    }catch{return unavailable("private_mcp_unreachable");}
  }
};
