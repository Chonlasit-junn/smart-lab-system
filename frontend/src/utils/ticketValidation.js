export const TICKET_SUBJECT_MAX_LENGTH = 255;
export const TICKET_MESSAGE_MAX_LENGTH = 5000;

export function countTicketCharacters(value) {
  return Array.from(value ?? '').length;
}

export function limitTicketText(value, maxLength) {
  return Array.from(value ?? '').slice(0, maxLength).join('');
}

export function getTicketErrorMessage(error, translate) {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    const longField = detail.find((item) => item?.type === 'string_too_long')?.loc?.at(-1);
    if (longField === 'subject') return translate('common.ticketSubjectTooLong');
    if (longField === 'message') return translate('common.ticketMessageTooLong');
    if (detail.some((item) => ['missing', 'string_too_short'].includes(item?.type))) {
      return translate('common.requiredFields');
    }
  }

  if (typeof detail === 'string' && detail.trim() && detail.length <= 300) {
    return detail;
  }
  return translate('common.ticketSendFailed');
}
