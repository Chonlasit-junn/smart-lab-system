const POINT_REASON_MESSAGE_KEYS = {
  daily_bonus: "user.dailyBonusReason",
  no_show: "user.noShowReason",
  forbidden_app: "user.forbiddenProgramReason",
  late_cancel: "user.lateCancelReason",
  complete_session: "user.sessionCompletedReason",
  admin_grant: "user.adminPointAdjustmentReason",
};

export function getPointReasonLabel(reason, t) {
  const messageKey = POINT_REASON_MESSAGE_KEYS[reason];
  return messageKey ? t(messageKey) : reason || t("common.notSpecified");
}
