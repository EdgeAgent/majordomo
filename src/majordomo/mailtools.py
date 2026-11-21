"""Mail tools: read, search, draft, and send email.

The tools sit behind one injectable backend, mirroring the web tools.
Three backends ship:

- :class:`FakeMailBackend` — a seeded mailbox of clearly-fake messages
  for the demo, the tests, and offline runs. Sends are recorded in
  memory and stamped fake; nothing leaves the machine.
- :class:`ImapSmtpBackend` — the real thing, standard library only
  (``imaplib`` + ``smtplib``), built from the ``MAJORDOMO_MAIL_*``
  settings.
- :class:`UnconfiguredMailBackend` — what a live run without mail
  settings gets: every call raises an honest "not configured" error
  instead of pretending to check a mailbox that does not exist.

Reading is free (read-only tools). Drafting writes a file into the
workspace and sending touches the outside world, so both are acting
tools and pass the approval gate like every other write.
"""

from __future__ import annotations

import email
import email.policy
import imaplib
import re
import smtplib
from contextlib import suppress
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from .config import Settings
from .filetools import Workspace
from .tools import Tool, ToolError, ToolRegistry

NOT_CONFIGURED = "Mail is not configured — set MAJORDOMO_MAIL_* settings."


class MailError(RuntimeError):
    """A mail operation failed; the message says why."""


@dataclass
class MailMessage:
    """One message, as the tools present it."""

    id: str
    sender: str
    to: str
    subject: str
    date: str
    body: str


class MailBackend(Protocol):
    """Anything that can list, read, search, and send mail."""

    def list_messages(self, limit: int = 10) -> list[MailMessage]: ...

    def read_message(self, message_id: str) -> MailMessage: ...

    def search(self, query: str) -> list[MailMessage]: ...

    def send(self, to: str, subject: str, body: str) -> str: ...


def _seed_messages() -> list[MailMessage]:
    return [
        MailMessage(
            id="fake-1",
            sender="Ada Lovelace <ada@example.com>",
            to="you@example.com",
            subject="Notes on the Analytical Engine",
            date="Tue, 21 Nov 2026 09:00:00 +0000",
            body=(
                "(fake message) The engine weaves algebraic patterns, just as the "
                "loom weaves flowers and leaves. This is a canned message from the "
                "fake mail backend — connect real mail settings for a live inbox."
            ),
        ),
        MailMessage(
            id="fake-2",
            sender="Grace Hopper <grace@example.com>",
            to="you@example.com",
            subject="Found a moth in the relay",
            date="Tue, 21 Nov 2026 09:05:00 +0000",
            body=(
                "(fake message) An actual moth, taped into the logbook. The "
                "compiler team sends its regards. Another canned message from "
                "the fake mail backend."
            ),
        ),
        MailMessage(
            id="fake-3",
            sender="The Demo Gazette <news@example.com>",
            to="you@example.com",
            subject="Your fake inbox is ready",
            date="Tue, 21 Nov 2026 09:10:00 +0000",
            body=(
                "(fake message) This mailbox exists so the mail tools can be "
                "tried end to end with no account and no network. Sends are "
                "recorded in memory and stamped fake; nothing is delivered."
            ),
        ),
    ]


class FakeMailBackend:
    """A seeded mailbox for offline runs. Sends are recorded, never sent."""

    name = "fake"

    def __init__(self, messages: list[MailMessage] | None = None) -> None:
        self._messages = list(messages) if messages is not None else _seed_messages()
        self.sent: list[dict[str, str]] = []

    def list_messages(self, limit: int = 10) -> list[MailMessage]:
        return self._messages[: max(0, int(limit))]

    def read_message(self, message_id: str) -> MailMessage:
        for message in self._messages:
            if message.id == message_id:
                return message
        raise MailError(f"No message with id {message_id!r} in the fake mailbox.")

    def search(self, query: str) -> list[MailMessage]:
        needle = query.lower()
        return [
            message
            for message in self._messages
            if needle in message.sender.lower()
            or needle in message.subject.lower()
            or needle in message.body.lower()
        ]

    def send(self, to: str, subject: str, body: str) -> str:
        self.sent.append({"to": to, "subject": subject, "body": body, "fake": "yes"})
        return (
            f"(fake mail backend) Recorded a fake send to {to} with subject "
            f"{subject!r}. Nothing was delivered."
        )


class UnconfiguredMailBackend:
    """Every call is the same honest error: mail was never set up."""

    name = "unconfigured"

    def list_messages(self, limit: int = 10) -> list[MailMessage]:
        raise ToolError(NOT_CONFIGURED)

    def read_message(self, message_id: str) -> MailMessage:
        raise ToolError(NOT_CONFIGURED)

    def search(self, query: str) -> list[MailMessage]:
        raise ToolError(NOT_CONFIGURED)

    def send(self, to: str, subject: str, body: str) -> str:
        raise ToolError(NOT_CONFIGURED)


class ImapSmtpBackend:
    """Real mail over IMAP (read) and SMTP (send), standard library only."""

    name = "imap-smtp"

    def __init__(
        self,
        *,
        address: str,
        username: str,
        password: str,
        imap_host: str,
        smtp_host: str,
        smtp_port: int = 587,
    ) -> None:
        self.address = address
        self.username = username
        self.password = password
        self.imap_host = imap_host
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port

    def _connect(self) -> imaplib.IMAP4_SSL:
        try:
            client = imaplib.IMAP4_SSL(self.imap_host)
            client.login(self.username, self.password)
            client.select("INBOX", readonly=True)
            return client
        except Exception as exc:
            raise MailError(f"Could not connect to IMAP at {self.imap_host}: {exc}") from exc

    def _fetch(self, client: imaplib.IMAP4_SSL, seq: bytes) -> MailMessage:
        status, data = client.fetch(seq, "(RFC822)")
        if status != "OK" or not data or not isinstance(data[0], tuple):
            raise MailError(f"IMAP fetch failed for message {seq.decode(errors='replace')}.")
        raw = data[0][1]
        if not isinstance(raw, bytes):
            raise MailError("IMAP returned an unexpected payload.")
        return _parse_message(seq.decode(), raw)

    def list_messages(self, limit: int = 10) -> list[MailMessage]:
        client = self._connect()
        try:
            status, data = client.search(None, "ALL")
            if status != "OK":
                raise MailError("IMAP search failed.")
            seqs = data[0].split() if data and data[0] else []
            newest = list(reversed(seqs))[: max(0, int(limit))]
            return [self._fetch(client, seq) for seq in newest]
        except MailError:
            raise
        except Exception as exc:
            raise MailError(f"Listing mail failed: {exc}") from exc
        finally:
            _close_quietly(client)

    def read_message(self, message_id: str) -> MailMessage:
        if not message_id.isdigit():
            raise MailError(f"No message with id {message_id!r}.")
        client = self._connect()
        try:
            return self._fetch(client, message_id.encode())
        except MailError:
            raise
        except Exception as exc:
            raise MailError(f"Reading message {message_id} failed: {exc}") from exc
        finally:
            _close_quietly(client)

    def search(self, query: str) -> list[MailMessage]:
        client = self._connect()
        try:
            escaped = query.replace("\\", "\\\\").replace('"', '\\"')
            status, data = client.search(None, "TEXT", f'"{escaped}"')
            if status != "OK":
                raise MailError("IMAP search failed.")
            seqs = data[0].split() if data and data[0] else []
            return [self._fetch(client, seq) for seq in reversed(seqs)][:25]
        except MailError:
            raise
        except Exception as exc:
            raise MailError(f"Searching mail failed: {exc}") from exc
        finally:
            _close_quietly(client)

    def send(self, to: str, subject: str, body: str) -> str:
        message = EmailMessage()
        message["From"] = self.address
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as smtp:
                smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(message)
        except Exception as exc:
            raise MailError(f"Sending via SMTP at {self.smtp_host} failed: {exc}") from exc
        return f"Sent to {to} with subject {subject!r} via {self.smtp_host}."


def _close_quietly(client: imaplib.IMAP4_SSL) -> None:
    with suppress(Exception):  # closing is best-effort
        client.logout()


def _parse_message(message_id: str, raw: bytes) -> MailMessage:
    parsed = email.message_from_bytes(raw, policy=email.policy.default)
    body = ""
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/plain":
                content = part.get_content()
                body = content if isinstance(content, str) else str(content)
                break
    else:
        try:
            content = parsed.get_content()
        except Exception:  # noqa: BLE001 - a non-text payload has no readable body
            content = ""
        body = content if isinstance(content, str) else str(content)
    return MailMessage(
        id=message_id,
        sender=str(parsed.get("From", "")),
        to=str(parsed.get("To", "")),
        subject=str(parsed.get("Subject", "")),
        date=str(parsed.get("Date", "")),
        body=body.strip(),
    )


def mail_is_configured(settings: Settings) -> bool:
    """True when every setting the IMAP/SMTP backend needs is present."""
    return bool(
        settings.mail_address
        and settings.mail_username
        and settings.mail_password
        and settings.mail_imap_host
        and settings.mail_smtp_host
    )


def build_mail_backend(settings: Settings, offline: bool) -> MailBackend:
    """Pick the mail backend the way the web tools pick theirs.

    Offline (fake provider) always gets the fake mailbox; a live run
    gets IMAP/SMTP when configured and the honest unconfigured backend
    otherwise.
    """
    if offline:
        return FakeMailBackend()
    if mail_is_configured(settings):
        return ImapSmtpBackend(
            address=str(settings.mail_address),
            username=str(settings.mail_username),
            password=str(settings.mail_password),
            imap_host=str(settings.mail_imap_host),
            smtp_host=str(settings.mail_smtp_host),
            smtp_port=settings.mail_smtp_port,
        )
    return UnconfiguredMailBackend()


def _summary(message: MailMessage) -> str:
    return f"{message.id} — {message.date} — From: {message.sender} — Subject: {message.subject}"


def _full(message: MailMessage) -> str:
    return (
        f"From: {message.sender}\nTo: {message.to}\nDate: {message.date}\n"
        f"Subject: {message.subject}\n\n{message.body}"
    )


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "draft"


@dataclass
class _Drafts:
    """Uniqueness helper state for draft file names."""

    workspace: Workspace
    used: set[str] = field(default_factory=set)

    def next_path(self, subject: str) -> str:
        base = f"drafts/draft-{_slug(subject)}"
        candidate = f"{base}.txt"
        counter = 2
        while candidate in self.used or _exists(self.workspace, candidate):
            candidate = f"{base}-{counter}.txt"
            counter += 1
        self.used.add(candidate)
        return candidate


def _exists(workspace: Workspace, relative: str) -> bool:
    try:
        return workspace.resolve(relative).exists()
    except ValueError:
        return False


def register_mail_tools(registry: ToolRegistry, backend: MailBackend, workspace: Workspace) -> None:
    """Add mail_list / mail_read / mail_search / mail_draft / mail_send."""
    drafts = _Drafts(workspace)

    def list_mail(limit: int = 10) -> str:
        messages = backend.list_messages(limit)
        if not messages:
            return "The inbox is empty."
        return "\n".join(_summary(message) for message in messages)

    def read_mail(message_id: str) -> str:
        return _full(backend.read_message(message_id))

    def search_mail(query: str) -> str:
        messages = backend.search(query)
        if not messages:
            return f"No messages match {query!r}."
        return "\n".join(_summary(message) for message in messages)

    def draft_mail(to: str, subject: str, body: str) -> str:
        relative = drafts.next_path(subject)
        content = f"To: {to}\nSubject: {subject}\n\n{body}\n"
        path = workspace.write(relative, content)
        return f"Draft saved to {path} (workspace path {relative})."

    def send_mail(to: str, subject: str, body: str) -> str:
        return backend.send(to, subject, body)

    registry.register(
        Tool(
            name="mail_list",
            description="List the most recent messages in the inbox (id, date, sender, subject).",
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "required": [],
            },
            handler=list_mail,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="mail_read",
            description="Read one message in full, by the id from mail_list or mail_search.",
            parameters={
                "type": "object",
                "properties": {"message_id": {"type": "string"}},
                "required": ["message_id"],
            },
            handler=read_mail,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="mail_search",
            description="Search the mailbox for a word or phrase in sender, subject, or body.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=search_mail,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="mail_draft",
            description="Save an email draft as a file in the workspace drafts/ area. Does not send.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
            handler=draft_mail,
            read_only=False,
        )
    )
    registry.register(
        Tool(
            name="mail_send",
            description="Send an email now. Acting tool: needs approval for this run.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
            handler=send_mail,
            read_only=False,
        )
    )
