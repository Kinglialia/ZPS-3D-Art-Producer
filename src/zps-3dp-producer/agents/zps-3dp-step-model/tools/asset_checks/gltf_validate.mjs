// Khronos glTF-Validator through its npm package (the package is a JS library, no CLI).
// Usage: node gltf_validate.mjs <file.glb|file.gltf>
// stdout: the validator's JSON report (same shape as `gltf_validator -o`).
// Exit codes: 0 report printed, 2 package not found (prints {"error": "module_not_found"}),
//             3 validator rejected the input (prints {"error": ...}), 1 usage / read error.
// Package lookup: GLTF_VALIDATOR_MODULE (path to the package folder), normal node resolution,
// then the global npm folder next to this node binary, then `npm root -g`.
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);

function loadValidator() {
  const tries = [];
  if (process.env.GLTF_VALIDATOR_MODULE) tries.push(process.env.GLTF_VALIDATOR_MODULE);
  tries.push("gltf-validator");
  tries.push(path.join(path.dirname(process.execPath), "..", "lib", "node_modules", "gltf-validator"));
  try {
    const root = execSync("npm root -g", { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    if (root) tries.push(path.join(root, "gltf-validator"));
  } catch { /* npm not available */ }
  for (const t of tries) {
    try { return require(t); } catch { /* try next */ }
  }
  return null;
}

const file = process.argv[2];
if (!file) {
  console.error("usage: node gltf_validate.mjs <file.glb|file.gltf>");
  process.exit(1);
}
const validator = loadValidator();
if (!validator) {
  console.log(JSON.stringify({ error: "module_not_found", hint: "npm i -g gltf-validator" }));
  process.exit(2);
}
let bytes;
try {
  bytes = new Uint8Array(fs.readFileSync(file));
} catch (e) {
  console.error(String(e));
  process.exit(1);
}
const dir = path.dirname(path.resolve(file));
validator.validateBytes(bytes, {
  uri: path.basename(file),
  maxIssues: 200,
  externalResourceFunction: (uri) =>
    new Promise((resolve, reject) => {
      fs.readFile(path.resolve(dir, decodeURIComponent(uri)), (err, data) => (err ? reject(String(err)) : resolve(data)));
    }),
}).then(
  (report) => { console.log(JSON.stringify(report)); process.exit(0); },
  (err) => { console.log(JSON.stringify({ error: String(err) })); process.exit(3); },
);
