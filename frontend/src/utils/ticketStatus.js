export const TICKET_REPLY_STATUS_OPTIONS = ["received", "in_progress", "resolved"];

const REPLY_STATUS_PRESENTATION = {
  received: { labelKey: "common.ticketStatusReceived", color: "warning" },
  in_progress: { labelKey: "common.ticketStatusInProgress", color: "info" },
  resolved: { labelKey: "common.ticketStatusResolved", color: "success" },
};

const TICKET_STATUS_BY_REPLY_STATUS = {
  received: "open",
  in_progress: "in_progress",
  resolved: "closed",
};

export function getTicketReplyStatus(reply) {
  if (TICKET_REPLY_STATUS_OPTIONS.includes(reply?.status)) return reply.status;
  return reply?.is_resolved ? "resolved" : "in_progress";
}

export function getTicketReplyStatusPresentation(status) {
  return REPLY_STATUS_PRESENTATION[status] ?? REPLY_STATUS_PRESENTATION.in_progress;
}

export function getTicketStatusForReply(status) {
  return TICKET_STATUS_BY_REPLY_STATUS[status] ?? "in_progress";
}

export function getInitialTicketReplyStatus(ticket) {
  const replies = ticket?.replies ?? [];
  if (replies.length > 0) return getTicketReplyStatus(replies[replies.length - 1]);
  if (ticket?.status === "closed") return "resolved";
  if (ticket?.status === "in_progress") return "in_progress";
  return "received";
}
