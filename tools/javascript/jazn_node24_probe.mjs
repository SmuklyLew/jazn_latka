const major = Number(process.versions.node.split(".", 1)[0]);
const awaited = await Promise.resolve("esm");
const payload = {
  ok:
    major === 24 &&
    awaited === "esm" &&
    typeof structuredClone === "function" &&
    typeof import.meta.url === "string",
  runtime: process.release?.name ?? "",
  node: process.versions.node,
  major,
  platform: process.platform,
  arch: process.arch,
  esm: true
};
console.log(JSON.stringify(payload));
if (!payload.ok) process.exitCode = 2;
