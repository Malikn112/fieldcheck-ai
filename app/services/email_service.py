"""
Email service — delivers a completed inspection's HTML report to the
inspector's email address.

Mirrors the vision_engine.py mock-mode pattern: by default (EMAIL_MOCK_MODE=
true) no real SMTP connection is ever attempted. Instead, the "sent" email is
written to disk under `REPORT_OUTPUT_DIR/mock_outbox/` so the full
login -> capture -> upload -> "email me the report" flow (web or Android) is
fully demoable without any mail credentials. Setting EMAIL_MOCK_MODE=false
and configuring SMTP_* switches to a real `smtplib` send.

This module never raises out of `send_inspection_report_email` for
expected failure modes (bad SMTP config, network error, etc.) — it always
returns an `EmailSendResult` so callers (the inspection pipeline) can record
the outcome without risking the inspection's own COMPLETED status.
"""
from __future__ import annotations

import logging
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from app.config import settings
from app.models.inspection import Inspection
from app.services.report_service import render_inspection_html

logger = logging.getLogger("fieldcheck.email")

# Deliberately simple — this is a client-side-friendly sanity check, not a
# full RFC 5322 validator. Good enough to catch typos before we either try
# to send mail or write a mock outbox file with a garbage name.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailConfigError(Exception):
    """Raised when EMAIL_MOCK_MODE=false but SMTP is not fully configured."""


@dataclass
class EmailSendResult:
    sent: bool
    mock: bool
    detail: str


def is_valid_email(value: str | None) -> bool:
    return bool(value and _EMAIL_RE.match(value.strip()))


def _build_message(inspection: Inspection, html_report: str) -> MIMEMultipart:
    condition = inspection.overall_condition.value if inspection.overall_condition else "PENDING"
    subject = f"[FieldCheck AI] Inspection Report — {condition} — {inspection.id[:8]}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_address}>"
    msg["To"] = inspection.inspector_email

    plain = (
        f"FieldCheck AI inspection report for {inspection.original_filename}\n"
        f"Inspection ID: {inspection.id}\n"
        f"Overall condition: {condition}\n\n"
        f"{inspection.overall_summary or ''}\n\n"
        "This is an HTML report — please view it in an email client that renders HTML, "
        "or open the FieldCheck AI dashboard to view it online."
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_report, "html"))
    return msg


async def _send_mock(inspection: Inspection, html_report: str) -> EmailSendResult:
    """Write the "sent" email to a local mock outbox instead of using SMTP."""
    outbox_dir = settings.report_output_path / "mock_outbox"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_recipient = re.sub(r"[^a-zA-Z0-9._-]", "_", inspection.inspector_email or "unknown")
    path = outbox_dir / f"{ts}_{inspection.id}_{safe_recipient}.html"
    path.write_text(html_report, encoding="utf-8")
    detail = f"[MOCK EMAIL] would have sent to {inspection.inspector_email}; saved to {path}"
    logger.info(detail)
    return EmailSendResult(sent=True, mock=True, detail=detail)


def _send_smtp_blocking(inspection: Inspection, html_report: str) -> EmailSendResult:
    """Blocking smtplib call — run via asyncio.to_thread from the async
    entrypoint so it doesn't stall the event loop."""
    if not settings.email_smtp_configured:
        raise EmailConfigError(
            "EMAIL_MOCK_MODE=false but SMTP_HOST/SMTP_FROM_ADDRESS are not configured."
        )

    msg = _build_message(inspection, html_report)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from_address, [inspection.inspector_email], msg.as_string())

    detail = f"Sent via SMTP ({settings.smtp_host}) to {inspection.inspector_email}"
    logger.info(detail)
    return EmailSendResult(sent=True, mock=False, detail=detail)


async def send_inspection_report_email(inspection: Inspection) -> EmailSendResult:
    """Render the inspection's HTML report and email it to
    `inspection.inspector_email`. Always returns an EmailSendResult — never
    raises for expected failure modes, so the caller can safely record the
    outcome on the Inspection row without risking its analysis results."""
    if not is_valid_email(inspection.inspector_email):
        detail = f"No valid inspector_email set for inspection {inspection.id}; skipping."
        logger.warning(detail)
        return EmailSendResult(sent=False, mock=settings.email_mock_mode, detail=detail)

    html_report = render_inspection_html(inspection)

    if settings.email_mock_mode:
        return await _send_mock(inspection, html_report)

    import asyncio

    try:
        return await asyncio.to_thread(_send_smtp_blocking, inspection, html_report)
    except Exception as exc:  # noqa: BLE001 — email failures must never propagate
        detail = f"Failed to send report email to {inspection.inspector_email}: {exc}"
        logger.error(detail)
        return EmailSendResult(sent=False, mock=False, detail=detail)
