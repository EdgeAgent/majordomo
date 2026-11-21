"""Media tools: image and video generation through Muse4AI.

Majordomo does not generate media itself here — it drives a separate
local app, `Muse4AI <https://github.com/andrew-babo/muse4ai>`_ (MIT,
by Andrew Babo), which runs on the same machine and queues image and
video generations on the operator's own signed-in Muse session.
Muse4AI serves a small REST API (default ``http://127.0.0.1:47821``);
this module is a standard-library-only client for it plus the tool
registrations. No Muse4AI code is copied into this repository — the
credit, and the engine, are entirely theirs.

The contract coded against is Muse4AI's published OpenAPI document
(``desktop/src/shared/api/openapi.ts`` in that repo, read 2026-11-21):

- ``POST /v1/jobs`` with ``{"kind": "image"|"video", "prompt": …}``
  answers 202 with ``{"jobs": [Job, …]}``.
- A Job carries ``id``, ``kind``, ``status`` (one of ``queued``,
  ``running``, ``needs_review``, ``succeeded``, ``failed``,
  ``cancelled``), an optional ``error`` (``{"code", "message"}``), and
  ``outputs`` — each with ``asset_id``, ``kind``, a signed
  ``download_url`` (valid ~60 minutes), and, for Muse videos, a
  ``conversation_id``.
- ``POST /v1/assets/{id}/extend`` answers 202 with
  ``{"chain": ExtendChain, "jobs": […]}``; the chain is polled at
  ``GET /v1/extend-chains/{id}`` and ends ``completed``, ``stopped``,
  ``cancelled``, or ``needs_review``, with ``latest_output`` holding
  the longest finished video.
- Errors are RFC 9457 problem JSON (``detail`` + a stable ``code``).

The one shape the OpenAPI document leaves unspecified is the
``GET /v1/jobs`` list body; the client accepts either ``{"jobs": […]}``
or a bare list, defensively.

Reading (status, list, get) is free. Generating and extending spend
the operator's Muse session — one generation each — so those tools
are acting tools and pass the approval gate like every other write.
With no API key set, or the app not running, every tool says exactly
that instead of inventing a result. The key is only ever sent in the
``Authorization`` header: it is never logged, printed, or included in
a tool result or an error message.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from .config import Settings
from .tools import Tool, ToolRegistry

DEFAULT_BASE_URL = "http://127.0.0.1:47821"

NO_KEY = (
    "No Muse4AI API key is configured — create one in the Muse4AI app "
    "(Settings → API & agent) and set MAJORDOMO_MUSE4AI_KEY. "
    "Majordomo never sees or stores your Muse login itself."
)

# A job in one of these states will not move again on its own:
# succeeded/failed/cancelled are final, and needs_review waits for a
# human in the Muse4AI app.
TERMINAL_JOB_STATUSES = frozenset({"succeeded", "failed", "cancelled", "needs_review"})
TERMINAL_CHAIN_STATUSES = frozenset({"completed", "stopped", "cancelled", "needs_review"})

SleepFn = Callable[[float], None]
NowFn = Callable[[], float]
Opener = Callable[..., Any]


class MediaError(RuntimeError):
    """A Muse4AI call failed; the message says why, honestly."""


class Muse4AIClient:
    """A tiny stdlib client for the Muse4AI local REST API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        *,
        request_timeout: float = 30.0,
        opener: Opener | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or None
        self.request_timeout = request_timeout
        self._opener = opener or urllib.request.urlopen

    @property
    def configured(self) -> bool:
        """True when an API key is set (health needs none; jobs do)."""
        return self.api_key is not None

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None, *, auth: bool = True
    ) -> Any:
        if auth and not self.api_key:
            raise MediaError(NO_KEY)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if auth and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with self._opener(request, timeout=self.request_timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise MediaError(
                f"Muse4AI is not reachable at {self.base_url} ({reason}). "
                "Is the Muse4AI app running on this machine?"
            ) from exc
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MediaError(f"Muse4AI answered {path} with a non-JSON body.") from exc
        return parsed

    def _http_error(self, exc: urllib.error.HTTPError) -> MediaError:
        detail = ""
        code = ""
        try:
            problem = json.loads(exc.read() or b"")
            if isinstance(problem, dict):
                detail = str(problem.get("detail") or problem.get("title") or "")
                code = str(problem.get("code") or "")
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = ""
        if exc.code == 401:
            return MediaError(
                "Muse4AI rejected the API key (401 Unauthorized) — check that "
                "MAJORDOMO_MUSE4AI_KEY matches a key created in the Muse4AI "
                "app under Settings → API & agent."
            )
        suffix = f": {detail}" if detail else ""
        if code:
            suffix += f" (code {code})"
        return MediaError(f"Muse4AI returned HTTP {exc.code} for this call{suffix}.")

    # -- endpoints ------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """GET /v1/health — liveness; needs no key."""
        result = self._request("GET", "/v1/health", auth=False)
        return result if isinstance(result, dict) else {}

    def status(self) -> dict[str, Any]:
        """GET /v1/status — capabilities, accounts, this key's limits."""
        result = self._request("GET", "/v1/status")
        return result if isinstance(result, dict) else {}

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        """GET /v1/jobs — this key's jobs, newest first."""
        query = urllib.parse.urlencode({"limit": max(1, int(limit))})
        result = self._request("GET", f"/v1/jobs?{query}")
        if isinstance(result, dict):
            jobs = result.get("jobs")
            return [job for job in jobs if isinstance(job, dict)] if isinstance(jobs, list) else []
        if isinstance(result, list):
            return [job for job in result if isinstance(job, dict)]
        return []

    def get_job(self, job_id: str) -> dict[str, Any]:
        """GET /v1/jobs/{id} — one job, outputs included."""
        result = self._request("GET", f"/v1/jobs/{urllib.parse.quote(job_id, safe='')}")
        if not isinstance(result, dict):
            raise MediaError(f"Muse4AI returned an unexpected body for job {job_id!r}.")
        return result

    def create_job(self, kind: str, prompt: str) -> dict[str, Any]:
        """POST /v1/jobs — queue one generation; returns the first job."""
        result = self._request("POST", "/v1/jobs", {"kind": kind, "prompt": prompt})
        jobs = result.get("jobs") if isinstance(result, dict) else None
        if isinstance(jobs, list) and jobs and isinstance(jobs[0], dict):
            return jobs[0]
        raise MediaError("Muse4AI accepted the request but returned no job.")

    def extend_asset(self, asset_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """POST /v1/assets/{id}/extend — returns (chain, jobs)."""
        result = self._request(
            "POST", f"/v1/assets/{urllib.parse.quote(asset_id, safe='')}/extend", {}
        )
        if not isinstance(result, dict) or not isinstance(result.get("chain"), dict):
            raise MediaError("Muse4AI accepted the extend but returned no chain.")
        jobs = result.get("jobs")
        job_list = [job for job in jobs if isinstance(job, dict)] if isinstance(jobs, list) else []
        return result["chain"], job_list

    def get_chain(self, chain_id: str) -> dict[str, Any]:
        """GET /v1/extend-chains/{id} — one extend chain."""
        result = self._request("GET", f"/v1/extend-chains/{urllib.parse.quote(chain_id, safe='')}")
        chain = result.get("chain") if isinstance(result, dict) else None
        if isinstance(chain, dict):
            return chain
        if isinstance(result, dict):
            return result
        raise MediaError(f"Muse4AI returned an unexpected body for chain {chain_id!r}.")

    # -- waiting --------------------------------------------------------

    def wait_for_job(
        self,
        job_id: str,
        *,
        timeout: float,
        interval: float = 2.0,
        sleep: SleepFn = time.sleep,
        now: NowFn = time.monotonic,
    ) -> tuple[dict[str, Any], bool]:
        """Poll a job to a terminal state. Returns (job, finished)."""
        deadline = now() + max(0.0, timeout)
        job = self.get_job(job_id)
        while str(job.get("status", "")) not in TERMINAL_JOB_STATUSES:
            if now() >= deadline:
                return job, False
            sleep(max(0.0, interval))
            job = self.get_job(job_id)
        return job, True

    def wait_for_chain(
        self,
        chain_id: str,
        *,
        timeout: float,
        interval: float = 2.0,
        sleep: SleepFn = time.sleep,
        now: NowFn = time.monotonic,
    ) -> tuple[dict[str, Any], bool]:
        """Poll an extend chain to a terminal state. (chain, finished)."""
        deadline = now() + max(0.0, timeout)
        chain = self.get_chain(chain_id)
        while str(chain.get("status", "")) not in TERMINAL_CHAIN_STATUSES:
            if now() >= deadline:
                return chain, False
            sleep(max(0.0, interval))
            chain = self.get_chain(chain_id)
        return chain, True


def build_media_client(settings: Settings) -> Muse4AIClient:
    """The client the runtime wires in, from MAJORDOMO_MUSE4AI_* settings."""
    return Muse4AIClient(base_url=settings.muse4ai_url, api_key=settings.muse4ai_key)


def _output_line(output: dict[str, Any]) -> str:
    parts = [f"asset {output.get('asset_id', '?')} ({output.get('kind', '?')})"]
    filename = output.get("filename")
    if filename:
        parts.append(str(filename))
    download = output.get("download_url")
    if download:
        parts.append(f"download (signed link, ~60 min): {download}")
    conversation = output.get("conversation_id")
    if conversation:
        parts.append(f"conversation {conversation}")
    return " — ".join(parts)


def _job_summary(job: dict[str, Any]) -> str:
    prompt = str(job.get("prompt") or "")
    if len(prompt) > 60:
        prompt = prompt[:57] + "…"
    return f"{job.get('id', '?')} — {job.get('kind', '?')} — {job.get('status', '?')} — {prompt!r}"


def _job_report(job: dict[str, Any], *, finished: bool, timeout: float) -> str:
    job_id = str(job.get("id", "?"))
    kind = str(job.get("kind", "media"))
    status = str(job.get("status", "unknown"))
    if not finished:
        return (
            f"{kind} job {job_id} is still running after {timeout:g} seconds "
            f"(status: {status}). It has not finished — check it later with "
            f"media_get_job using id {job_id}."
        )
    if status == "succeeded":
        lines = [f"{kind} job {job_id} succeeded."]
        outputs = job.get("outputs")
        if isinstance(outputs, list):
            lines.extend(_output_line(o) for o in outputs if isinstance(o, dict))
        if len(lines) == 1:
            lines.append("It reported no outputs.")
        return "\n".join(lines)
    if status == "failed":
        raw_error = job.get("error")
        error: dict[str, Any] = raw_error if isinstance(raw_error, dict) else {}
        code = error.get("code", "unknown")
        message = error.get("message", "no message given")
        return f"{kind} job {job_id} FAILED in Muse4AI ({code}: {message}). Nothing was made."
    if status == "needs_review":
        return (
            f"{kind} job {job_id} is waiting for a human in the Muse4AI app "
            "(needs_review). Nothing is final until it is reviewed there."
        )
    return f"{kind} job {job_id} ended with status {status}."


def _chain_report(chain: dict[str, Any], *, finished: bool, timeout: float) -> str:
    chain_id = str(chain.get("id", "?"))
    status = str(chain.get("status", "unknown"))
    if not finished:
        return (
            f"Extend chain {chain_id} is still running after {timeout:g} seconds "
            f"(status: {status}). The video is not extended yet."
        )
    if status == "completed":
        lines = [f"Extend chain {chain_id} completed."]
        latest = chain.get("latest_output")
        if isinstance(latest, dict):
            lines.append(f"Extended video: {_output_line(latest)}")
        return "\n".join(lines)
    if status == "needs_review":
        return f"Extend chain {chain_id} is waiting for a human in the Muse4AI app (needs_review)."
    reason = chain.get("stop_reason")
    suffix = f" ({reason})" if reason else ""
    return f"Extend chain {chain_id} ended with status {status}{suffix}."


def register_media_tools(
    registry: ToolRegistry,
    client: Muse4AIClient,
    *,
    timeout: float = 300.0,
    poll_interval: float = 2.0,
) -> None:
    """Add the media_status / media_* tools backed by ``client``.

    ``timeout`` bounds how long a generation or extend call polls
    before reporting the job as still running; nothing here ever
    reports a success the API did not return.
    """

    def media_status() -> str:
        try:
            client.health()
        except MediaError as exc:
            return f"Muse4AI media is NOT available: {exc}"
        lines = [f"Muse4AI is running at {client.base_url} (health OK)."]
        if not client.configured:
            lines.append(NO_KEY)
            return "\n".join(lines)
        try:
            status = client.status()
        except MediaError as exc:
            return "\n".join([*lines, f"But its status call failed: {exc}"])
        accounts = status.get("accounts")
        items = accounts.get("items") if isinstance(accounts, dict) else None
        if isinstance(items, list) and items:
            rendered = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                raw_quota = item.get("quota")
                quota: dict[str, Any] = raw_quota if isinstance(raw_quota, dict) else {}
                tier = quota.get("tier", "unknown")
                rendered.append(f"{item.get('alias', '?')} (quota: {tier})")
            if rendered:
                lines.append("Muse accounts: " + ", ".join(rendered))
        capabilities = status.get("capabilities")
        if isinstance(capabilities, dict) and capabilities:
            on = sorted(name for name, enabled in capabilities.items() if enabled)
            if on:
                lines.append("Capabilities on: " + ", ".join(on))
        return "\n".join(lines)

    def media_list_jobs(limit: int = 10) -> str:
        jobs = client.list_jobs(limit)
        if not jobs:
            return "No Muse4AI jobs found for this key."
        return "\n".join(_job_summary(job) for job in jobs)

    def media_get_job(job_id: str) -> str:
        job = client.get_job(job_id)
        lines = [_job_summary(job)]
        outputs = job.get("outputs")
        if isinstance(outputs, list):
            lines.extend(_output_line(o) for o in outputs if isinstance(o, dict))
        error = job.get("error")
        if isinstance(error, dict) and error:
            lines.append(f"error: {error.get('code', '?')}: {error.get('message', '')}")
        return "\n".join(lines)

    def _generate(kind: str, prompt: str) -> str:
        job = client.create_job(kind, prompt)
        job_id = str(job.get("id", ""))
        if not job_id:
            raise MediaError("Muse4AI accepted the request but returned a job with no id.")
        final, finished = client.wait_for_job(job_id, timeout=timeout, interval=poll_interval)
        return _job_report(final, finished=finished, timeout=timeout)

    def media_generate_image(prompt: str) -> str:
        return _generate("image", prompt)

    def media_generate_video(prompt: str) -> str:
        return _generate("video", prompt)

    def media_extend_video(asset_id: str) -> str:
        chain, _jobs = client.extend_asset(asset_id)
        chain_id = str(chain.get("id", ""))
        if not chain_id:
            raise MediaError("Muse4AI accepted the extend but returned a chain with no id.")
        final, finished = client.wait_for_chain(chain_id, timeout=timeout, interval=poll_interval)
        return _chain_report(final, finished=finished, timeout=timeout)

    registry.register(
        Tool(
            name="media_status",
            description=(
                "Check the local Muse4AI media app: is it running, which Muse "
                "accounts and capabilities does it report. Read-only."
            ),
            parameters={"type": "object", "properties": {}, "required": []},
            handler=media_status,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="media_list_jobs",
            description="List recent Muse4AI generation jobs for this key (id, kind, status).",
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "required": [],
            },
            handler=media_list_jobs,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="media_get_job",
            description=(
                "Get one Muse4AI job by id: status, outputs (asset ids and "
                "signed download links), and any error."
            ),
            parameters={
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
            handler=media_get_job,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="media_generate_image",
            description=(
                "Generate an image with Muse4AI on the user's own Muse session. "
                "Acting tool: needs approval for this run. Waits for the job and "
                "returns its status and output asset/download link."
            ),
            parameters={
                "type": "object",
                "properties": {"prompt": {"type": "string"}},
                "required": ["prompt"],
            },
            handler=media_generate_image,
            read_only=False,
        )
    )
    registry.register(
        Tool(
            name="media_generate_video",
            description=(
                "Generate a video with Muse4AI on the user's own Muse session. "
                "Acting tool: needs approval for this run. Waits for the job and "
                "returns its status and output asset/download link."
            ),
            parameters={
                "type": "object",
                "properties": {"prompt": {"type": "string"}},
                "required": ["prompt"],
            },
            handler=media_generate_video,
            read_only=False,
        )
    )
    registry.register(
        Tool(
            name="media_extend_video",
            description=(
                "Extend a finished Muse4AI video (by its output asset id) in its "
                "own Muse conversation. Acting tool: needs approval for this run."
            ),
            parameters={
                "type": "object",
                "properties": {"asset_id": {"type": "string"}},
                "required": ["asset_id"],
            },
            handler=media_extend_video,
            read_only=False,
        )
    )
