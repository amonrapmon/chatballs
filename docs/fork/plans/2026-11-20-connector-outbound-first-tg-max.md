# Outbound-first TG/MAX dialogs via API Connector

Status: implementation in PR, not a marketing sender.

## Scenario

A separate site/lead service already has a verified, purpose-limited opt-in
for a selected transport (Telegram or MAX). That service may use the provider's
own API to address a person by verified phone/transport ID and initiate contact,
without requiring that the person first message the business account.

The existing TG/MAX GREEN-API adapters observe provider
`outgoingMessageReceived` and forward an authenticated
`message.observed_outgoing` event to the Chatballs Connector.
Previously, Chatballs replied `409 unknown_conversation` if the recipient had
not yet sent an inbound message.

## Connector change (both transports, one implementation)

- A new current-epoch, authenticated, mirror-enabled, **personal-text-only**
  observation can bootstrap a native Contact, ConnectionIdentity and Conversation.
- The external **chat ID** addresses the private recipient route. The observed
  outgoing sender's `external_user_id` is **not** trusted as the contact's user
  ID: on outbound, the sender could be the operator's business account.
- New routes inherit the channel's operator visibility group and have
  `control_mode=HUMAN`, `expected_responder=CUSTOMER` and no assigned staff
  member or pending AI turn. The observed message retains `OPERATOR` author
  with no individual employee identity, and `EXTERNAL_OBSERVED` provenance.
- Staff receive a `NEW_DIALOG` notification. No outbound command is generated
  by ingesting the observation; sending to the provider has already happened.
- On existing routes, preserve the previous behavior. A newly initiated
  observation on a closed route opens a new conversation linked to its predecessor.
- Inbound and observed-outgoing bootstrap share the organization lock to
  prevent duplicate contacts or routes when the first reply and the first
  outgoing echo race each other.
- Replays are idempotent by event + provider-message ID. Never bootstrap groups,
  unsupported media, expired-pre-cutover observations, disabled integrations or
  cross-tenant routes.

Both adapter services use the same Connector event contract, so **no TG/MAX
adapter fork or additional database migration** is needed for this step.

## Separate lead outreach workflow (not implemented by mirroring)

The lead-facing sender owns a durable campaign/lead-job queue, per-channel
consent evidence, message variant selection, rate and dedup rules, a provider
recipient lookup, sending through the allowed business instance, waiting for
provider *delivery* status, and notifying/assigning an operator. A successful
send command alone does not imply that the message was delivered.

Recommended minimum state machine:

`consent_checked -> queued -> recipient_verified -> dispatched -> provider_accepted -> delivered | failed`

Save the exact consent terms, provenance, selected messenger and timestamp;
never treat `CheckAccount.exist` as consent. No automatic fallback to a
messenger not selected by the person. Randomized variants must not bypass
opt-out, consent or provider limits.

The Connector mirror is only the **conversation projection** of an already
provider-observed outgoing action. It neither grants permission to send nor
runs the lead queue itself.

## Validation

1. Enable `mirrorExternalOutgoingEnabled` separately for the TG/MAX
   integration; the epoch prevents old webhook imports.
2. Send a first outbound message from the business account with provider
   callback enabled. Confirm `message.observed_outgoing` is accepted as
   `202`, then confirm Contact + open conversation + one external-origin
   operator message and no Chatballs outbound command.
3. Send a guest reply and verify it joins the same personal route.
4. Check disabled mirror, pre-epoch event, duplicate/replay, closed-route
   follow-up, shared chat ID across separate integrations, and inbound/outbound
   concurrency tests.
5. Confirm that an external provider-origin message triggers a callback:
   `SendMessage` success alone is not evidence of a webhook or a dialog.

This change does **not** supply native MAX `web.max.ru` direct links.
GREEN-API `chatId` and the MAX web-dialog ID remain distinct.
