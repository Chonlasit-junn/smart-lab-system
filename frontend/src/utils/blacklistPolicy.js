import tr46 from "tr46";

// Domain contract v1: Unicode 16 UTS46, non-transitional, domain-only.
const IDNA_OPTIONS = Object.freeze({
  checkBidi: true, checkHyphens: true, checkJoiners: true,
  useSTD3ASCIIRules: true, verifyDNSLength: false,
  transitionalProcessing: false, ignoreInvalidPunycode: false,
});

function normalizeIPv4(host) {
  const parts = host.split(".");
  if (parts.length > 4) return null;
  const values = parts.map((input) => {
    let base = 10;
    if (input.startsWith("0x")) {
      base = 16;
      input = input.slice(2);
    } else if (input.length > 1 && input.startsWith("0")) {
      base = 8;
      input = input.slice(1);
    }
    const digits = { 10: /^[0-9]*$/u, 16: /^[0-9a-f]*$/u, 8: /^[0-7]*$/u }[base];
    return digits.test(input) ? (input ? Number.parseInt(input, base) : 0) : NaN;
  });
  if (values.some((value) => !Number.isFinite(value))
    || values.slice(0, -1).some((value) => value > 255)
    || values.at(-1) >= 256 ** (5 - values.length)) return null;
  const number = values.at(-1) + values.slice(0, -1)
    .reduce((sum, value, index) => sum + value * 256 ** (3 - index), 0);
  return [3, 2, 1, 0].map((index) => Math.floor(number / 256 ** index) % 256).join(".");
}

export function normalizeWebsiteDomain(value) {
  if (typeof value !== "string") return null;
  let raw = value.replace(/^[ \t\r\n\f\v]+|[ \t\r\n\f\v]+$/gu, "");
  if (!raw || [...raw].length > 4096 || /[\s\\\u0085]/u.test(raw)
    || [...raw].some((character) => character.charCodeAt(0) <= 32 || character.charCodeAt(0) === 127)) return null;
  try {
    const separator = raw.indexOf("://");
    if (separator >= 0) {
      if (!["http", "https"].includes(raw.slice(0, separator).toLowerCase())) return null;
      raw = raw.slice(separator + 3);
    }
    const authority = raw.split(/[/?#]/u, 1)[0];
    if (!authority || /[@%]/u.test(authority)) return null;
    let host = authority;
    let port = null;
    let ipv6 = false;
    if (authority.startsWith("[")) {
      const end = authority.indexOf("]");
      if (end < 0) return null;
      host = authority.slice(1, end);
      const suffix = authority.slice(end + 1);
      if (suffix) {
        if (!suffix.startsWith(":")) return null;
        port = suffix.slice(1);
      }
      ipv6 = true;
    } else if (authority.split(":").length > 2) {
      if (separator >= 0) return null;
      ipv6 = true;
    } else if (authority.includes(":")) {
      const split = authority.lastIndexOf(":");
      host = authority.slice(0, split);
      port = authority.slice(split + 1);
    }
    if (port !== null && (!/^[0-9]{1,5}$/u.test(port) || Number(port) > 65535)) return null;
    if (ipv6) return new URL(`http://[${host}]`).hostname;
    host = tr46.toASCII(host, IDNA_OPTIONS)?.replace(/\.$/u, "");
    if (!host || host.length > 253 || !host.split(".").every(
      (label) => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/u.test(label),
    )) return null;
    if (/^(?:[0-9]+|0x[0-9a-f]*)$/u.test(host.split(".").at(-1))) return normalizeIPv4(host);
    return host.includes(".") ? host : null;
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
