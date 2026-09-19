export function authConfig() {
  const token = localStorage.getItem("access_token");
  return token
    ? { headers: { Authorization: `Bearer ${token}` } }
    : {};
}
