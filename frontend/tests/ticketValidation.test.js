import test from 'node:test';
import assert from 'node:assert/strict';
import {
  countTicketCharacters,
  getTicketErrorMessage,
  limitTicketText,
  TICKET_MESSAGE_MAX_LENGTH,
  TICKET_SUBJECT_MAX_LENGTH,
} from '../src/utils/ticketValidation.js';

test('Ticket limits match backend field limits', () => {
  assert.equal(TICKET_SUBJECT_MAX_LENGTH, 255);
  assert.equal(TICKET_MESSAGE_MAX_LENGTH, 5000);
});

test('character counting and truncation count Unicode code points', () => {
  assert.equal(countTicketCharacters('A😀B'), 3);
  assert.equal(limitTicketText('A😀BC', 3), 'A😀B');
});

test('long subject validation errors are translated without echoing input', () => {
  const rawInput = 'secret user-entered ticket text';
  const translate = (key) => key;
  const message = getTicketErrorMessage({
    response: { data: { detail: [{
      type: 'string_too_long',
      loc: ['body', 'subject'],
      input: rawInput,
      ctx: { max_length: TICKET_SUBJECT_MAX_LENGTH },
    }] } },
  }, translate);

  assert.equal(message, 'common.ticketSubjectTooLong');
  assert.equal(message.includes(rawInput), false);
});

test('long message and required-field errors use friendly translations', () => {
  const translate = (key) => key;
  assert.equal(getTicketErrorMessage({
    response: { data: { detail: [{ type: 'string_too_long', loc: ['body', 'message'] }] } },
  }, translate), 'common.ticketMessageTooLong');
  assert.equal(getTicketErrorMessage({
    response: { data: { detail: [{ type: 'missing', loc: ['body', 'subject'] }] } },
  }, translate), 'common.requiredFields');
});

test('unstructured backend errors do not leak raw response objects', () => {
  const translate = (key) => key;
  assert.equal(getTicketErrorMessage({ response: { data: { detail: { secret: 'value' } } } }, translate), 'common.ticketSendFailed');
  assert.equal(getTicketErrorMessage({ response: { data: { detail: 'Service unavailable' } } }, translate), 'Service unavailable');
});
