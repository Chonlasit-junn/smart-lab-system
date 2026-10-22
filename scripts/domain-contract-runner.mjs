// Offline stdin/stdout bridge for cross-language regression checks.
import { normalizeWebsiteDomain, serializeBlacklistForm } from "../frontend/src/utils/blacklistPolicy.js";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const values = JSON.parse(input);
console.log(JSON.stringify(values.map((value) => {
  const domain = normalizeWebsiteDomain(value);
  return {
    domain,
    idempotent: domain === null || normalizeWebsiteDomain(domain) === domain,
    payload: domain === null ? null : serializeBlacklistForm({
      app_name: "Offline fixture", description: "", match_type: "website_domain", match_value: value,
    }).match_value,
  };
})));
