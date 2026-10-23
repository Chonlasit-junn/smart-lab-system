export function isPendingUser(users, userId) {
  return (Array.isArray(users) ? users : []).some(
    (user) => String(user.id) === String(userId),
  );
}
