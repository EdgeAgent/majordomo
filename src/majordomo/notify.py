"""Notifications out: one webhook POST, best effort.

Majordomo runs on your machine; your phone is somewhere else. When
something needs you — new mail worth a digest, a reminder nobody
acknowledged — a heads-up has to travel. The transport is a single
webhook: set ``MAJORDOMO_NOTIFY_WEBHOOK`` to any URL that accepts a
JSON POST and Majordomo sends

```json
{"title": "…", "body": "…", "source": "majordomo"}
```

That shape works with ntfy-style servers, generic webhook receivers,
and most automation inboxes (a Make/n8n/Zapier webhook URL is a fine
target). Notifications are **outbound only** — nothing here listens,
replies, or phones home anywhere else.

Best effort is the whole contract: a missing URL, a refused
connection, or a sad server is logged and reported as ``False`` —
never raised. A notification must not be able to break the daemon
tick that produced it.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from typing import Any

import structlog

log = structlog.get_logger(__name__)

Opener = Callable[..., Any]

_DEFAULT_TIMEOUT = 5.0


def send_notification(
    title: str,
    body: str,
    url: str | None,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    opener: Opener | None = None,
) -> bool:
    """POST one notification to ``url``. True only on a 2xx answer."""
    if not url:
        log.info("notify.skipped", reason="no webhook configured")
        return False
    payload = json.dumps({"title": title, "body": body, "source": "majordomo"}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
    except Exception as exc:  # noqa: BLE001 - best effort: any failure is a False, never a crash
        log.warning("notify.failed", error=str(exc))
        return False
    if 200 <= status < 300:
        log.info("notify.sent", title=title)
        return True
    log.warning("notify.failed", status=status)
    return False


class Notifier:
    """A configured (or absent) notification channel.

    The daemon and the web app hold one of these; ``notify`` is safe
    to call unconditionally — with no webhook set it is a logged no-op
    returning ``False``.
    """

    def __init__(
        self,
        url: str | None,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        opener: Opener | None = None,
    ) -> None:
        self.url = url or None
        self.timeout = timeout
        self.opener = opener

    @property
    def enabled(self) -> bool:
        return self.url is not None

    def notify(self, title: str, body: str) -> bool:
        return send_notification(title, body, self.url, timeout=self.timeout, opener=self.opener)
