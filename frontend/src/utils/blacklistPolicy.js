export function blacklistFormError(form) {
  if (!form.app_name.trim()) return "admin.appNameRequired";
  return null;
}

export function serializeBlacklistForm(form) {
  return {
    ...form,
    app_name: form.app_name.trim(),
    description: form.description.trim(),
    match_value: form.match_value.trim() || form.app_name.trim(),
  };
}
