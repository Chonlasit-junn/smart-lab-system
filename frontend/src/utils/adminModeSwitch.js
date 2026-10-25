const ADMIN_ROUTES = new Set([
  "/admin",
  "/admin/points",
  "/admin/points/policy",
  "/admin/roles",
  "/admin/devices",
  "/admin/reports",
  "/manage-labs",
  "/verify-users",
  "/blacklist",
  "/ticket",
  "/profile",
]);

export function canSwitchAdminMode(user) {
  return user?.roleName === "admin";
}

export function getAdminReturnPath(path) {
  return ADMIN_ROUTES.has(path) ? path : "/admin";
}
