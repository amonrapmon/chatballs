"""Shared SMTP delivery with factual outcomes; no raw provider errors escape."""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from django.conf import settings


@dataclass(frozen=True)
class MailOutcome:
    state: str
    error_code: str = ""


def failure_outcome(error, *, sending):
    # A final negative SMTP response proves non-acceptance. A lost connection
    # during DATA may hide the final 250 and cannot prove absence of delivery.
    rejected = isinstance(error, (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused))
    if rejected:
        return MailOutcome("FAILED", "SMTP_REJECTED")
    return MailOutcome("UNKNOWN" if sending else "FAILED", "TRANSPORT_ERROR")


def deliver_message(integration, outgoing):
    config = integration.config
    if not integration.is_active or not config.get("smtp_host") or not integration.secret:
        return MailOutcome("FAILED", "CONNECTION_UNAVAILABLE")
    client, sending = None, False
    try:
        host, port = config["smtp_host"], int(config.get("smtp_port") or 465)
        constructor = smtplib.SMTP_SSL if config.get("smtp_ssl", True) else smtplib.SMTP
        client = constructor(host, port, timeout=settings.CHATBALLS_AI_REQUEST_TIMEOUT)
        if not config.get("smtp_ssl", True):
            client.starttls()
        client.login(str(config.get("email", "")).strip().lower(), integration.secret)
        sending = True
        refused = client.send_message(outgoing)
        if refused:
            return MailOutcome("FAILED", "SMTP_REJECTED")
        # QUIT failure after the final 250 does not undo SMTP acceptance.
        return MailOutcome("SMTP_ACCEPTED")
    except (smtplib.SMTPException, OSError, TimeoutError, ValueError) as error:
        return failure_outcome(error, sending=sending)
    finally:
        if client is not None:
            try:
                client.quit()
            except (smtplib.SMTPException, OSError):
                client.close()


def continuation_message(letter):
    outgoing = EmailMessage()
    outgoing["From"] = str(letter.connection.config.get("email", "")).strip().lower()
    outgoing["To"] = letter.thread.recipient
    outgoing["Subject"] = letter.thread.subject
    outgoing["Message-ID"] = letter.mail_message_id
    if letter.in_reply_to:
        outgoing["In-Reply-To"] = letter.in_reply_to
    if letter.references:
        outgoing["References"] = " ".join(letter.references)
    outgoing.set_content(letter.message.text)
    return outgoing
