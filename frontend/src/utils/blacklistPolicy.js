// Website evidence is domain-only; never send URL paths, credentials or queries.
export function normalizeWebsiteDomain(value) {
  const raw = String(value || "").trim();
  if (!raw || raw.length > 4096 || /[\s\\]/u.test(raw)
    || [...raw].some((character) => character.charCodeAt(0) < 32)) return null;
  try {
    const url = new URL(raw.includes("://") ? raw : `https://${raw}`);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
    const host = url.hostname.toLowerCase().replace(/\.$/u, "");
    if (host.length > 253 || !host.includes(".")) return null;
    return host.split(".").every((label) => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/u.test(label))
      ? host : null;
  } catch {
    return null;
  }
}

export function blacklistFormError(form) {
  if (!form.app_name.trim()) return "admin.appNameRequired";
  if (form.match_type === "website_domain") {
    if (!form.match_value.trim()) return "admin.websiteDomainRequired";
    if (!normalizeWebsiteDomain(form.match_value)) return "admin.websiteDomainInvalid";
  }
  return null;
}

export function serializeBlacklistForm(form) {
  return {
    ...form,
    app_name: form.app_name.trim(),
    description: form.description.trim(),
    match_value: form.match_type === "website_domain"
      ? normalizeWebsiteDomain(form.match_value)
      : form.match_value.trim() || form.app_name.trim(),
  };
}
