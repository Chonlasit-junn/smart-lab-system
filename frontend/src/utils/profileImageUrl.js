const API_URL = import.meta.env?.VITE_API_URL;

export function profileImageUrl(profilePic, apiUrl = API_URL) {
  if (!profilePic) return undefined;
  const value = String(profilePic);
  if (/^https?:\/\//i.test(value)) return value;
  if (!apiUrl) return value;
  return `${apiUrl.replace(/\/+$/, "")}/${value.replace(/^\/+/, "")}`;
}
