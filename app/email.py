import smtplib
from email.message import EmailMessage

from flask import current_app


def send_email(to, subject, body):
    """Send a plain-text email.

    Under test the message is appended to app.extensions["mail_outbox"]
    instead. With no MAIL_SERVER configured (local dev) it's written to the
    log, so a reset link can be copied out of `docker compose logs web`.
    """
    config = current_app.config
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config["MAIL_DEFAULT_SENDER"] or config["MAIL_USERNAME"] or ""
    msg["To"] = to
    msg.set_content(body)

    if current_app.testing:
        current_app.extensions.setdefault("mail_outbox", []).append(msg)
        return

    if not config["MAIL_SERVER"]:
        current_app.logger.warning(
            "MAIL_SERVER not set; not sending email to %s:\n%s", to, body
        )
        return

    if config["MAIL_USE_SSL"]:
        smtp = smtplib.SMTP_SSL(config["MAIL_SERVER"], config["MAIL_PORT"], timeout=10)
    else:
        smtp = smtplib.SMTP(config["MAIL_SERVER"], config["MAIL_PORT"], timeout=10)
    with smtp:
        if not config["MAIL_USE_SSL"]:
            smtp.starttls()
        if config["MAIL_USERNAME"]:
            smtp.login(config["MAIL_USERNAME"], config["MAIL_PASSWORD"])
        smtp.send_message(msg)
