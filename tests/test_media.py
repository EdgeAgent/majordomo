"""Media tools: a fake Muse4AI server (stdlib http.server) speaking
the published REST contract, the client's honest failure modes, the
approval-gate classes, and the MAJORDOMO_MEDIA=off switch.

The secret used throughout is SECRET; several tests assert it never
appears in any tool output or error text.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from majordomo import media as media_module
from majordomo.config import Settings
from majordomo.mcp_server import handle_message
from majordomo.media import MediaError, Muse4AIClient, register_media_tools
from majordomo.providers import FakeProvider
from majordomo.runtime import build_runtime
from majordomo.tools import ToolError, ToolRegistry

SECRET = "msk_test_SECRET_do_not_leak"


class _FakeState:
    """The fake Muse4AI's whole world: jobs, chains, poll counts."""

    def __init__(self) -> None:
        self.expected_key = SECRET
        self.jobs: dict[str, dict[str, Any]] = {}
        self.job_polls: dict[str, int] = {}
        self.chains: dict[str, dict[str, Any]] = {}
        self.chain_polls: dict[str, int] = {}
        self.counter = 0


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if not key.startswith("_")}


class _FakeMuse4AIHandler(BaseHTTPRequestHandler):
    state = _FakeState()
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: Any) -> None:  # keep the test log quiet
        pass

    # -- plumbing ------------------------------------------------------

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _problem(self, status: int, code: str, detail: str) -> None:
        self._send_json(
            status,
            {
                "type": "about:blank",
                "title": code,
                "status": status,
                "detail": detail,
                "code": code,
                "request_id": "req-fake",
            },
        )

    def _authed(self) -> bool:
        if self.headers.get("Authorization") == f"Bearer {self.state.expected_key}":
            return True
        self._problem(401, "unauthorized", "Missing or invalid API key.")
        return False

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        parsed = json.loads(self.rfile.read(length) or b"{}")
        return parsed if isinstance(parsed, dict) else {}

    # -- job behaviour ---------------------------------------------------

    def _advance_job(self, job: dict[str, Any]) -> None:
        """One GET = one poll; the prompt picks the job's fate."""
        polls = self.state.job_polls.get(str(job["id"]), 0) + 1
        self.state.job_polls[str(job["id"])] = polls
        prompt = str(job.get("prompt", ""))
        if "never finishes" in prompt:
            job["status"] = "running"
            return
        if polls < 2:
            job["status"] = "running"
            return
        if "please fail" in prompt:
            job["status"] = "failed"
            job["error"] = {"code": "PROVIDER_ERROR", "message": "Muse reported a failure."}
            return
        kind = str(job["kind"])
        job["status"] = "succeeded"
        job["outputs"] = [
            {
                "asset_id": f"asset-{job['id']}",
                "kind": kind,
                "filename": f"{job['id']}.out",
                "download_url": f"http://127.0.0.1/dl/{job['id']}",
                "conversation_id": "mc_fake_conversation" if kind == "video" else None,
            }
        ]

    # -- routes ----------------------------------------------------------

    def do_GET(self) -> None:
        state = self.state
        if self.path == "/v1/health":
            self._send_json(200, {"ok": True})
            return
        if not self._authed():
            return
        if self.path == "/v1/status":
            self._send_json(
                200,
                {
                    "accounts": {
                        "items": [{"alias": "main", "quota": {"tier": "ok"}}],
                    },
                    "capabilities": {"muse.video.extend": True, "muse.image": True},
                },
            )
            return
        if self.path.startswith("/v1/jobs/"):
            job_id = self.path.removeprefix("/v1/jobs/").split("?")[0]
            job = state.jobs.get(job_id)
            if job is None:
                self._problem(404, "not_found", f"No job {job_id}.")
                return
            self._advance_job(job)
            self._send_json(200, _public_job(job))
            return
        if self.path.startswith("/v1/jobs"):
            jobs = [_public_job(job) for job in reversed(list(state.jobs.values()))]
            self._send_json(200, {"jobs": jobs})
            return
        if self.path.startswith("/v1/extend-chains/"):
            chain_id = self.path.removeprefix("/v1/extend-chains/").split("?")[0]
            chain = state.chains.get(chain_id)
            if chain is None:
                self._problem(404, "not_found", f"No chain {chain_id}.")
                return
            polls = state.chain_polls.get(chain_id, 0) + 1
            state.chain_polls[chain_id] = polls
            if polls >= 2:
                chain["status"] = "completed"
                chain["latest_output"] = {
                    "asset_id": f"asset-{chain_id}-long",
                    "kind": "video",
                    "download_url": f"http://127.0.0.1/dl/{chain_id}",
                    "conversation_id": "mc_fake_conversation",
                }
            self._send_json(200, chain)
            return
        self._problem(404, "not_found", "Unknown path.")

    def do_POST(self) -> None:
        state = self.state
        if not self._authed():
            return
        if self.path == "/v1/jobs":
            body = self._body()
            state.counter += 1
            job_id = f"job-{state.counter}"
            job: dict[str, Any] = {
                "id": job_id,
                "kind": body.get("kind", "image"),
                "prompt": body.get("prompt", ""),
                "status": "queued",
                "outputs": [],
                "error": None,
            }
            state.jobs[job_id] = job
            self._send_json(202, {"jobs": [_public_job(job)]})
            return
        if self.path.startswith("/v1/assets/") and self.path.endswith("/extend"):
            asset_id = self.path.removeprefix("/v1/assets/").removesuffix("/extend")
            known = any(
                output.get("asset_id") == asset_id
                for job in state.jobs.values()
                for output in job.get("outputs", [])
            )
            if not known:
                self._problem(404, "not_found", f"No asset {asset_id}.")
                return
            state.counter += 1
            chain_id = f"chain-{state.counter}"
            chain: dict[str, Any] = {
                "id": chain_id,
                "status": "running",
                "source_asset_id": asset_id,
                "latest_output": None,
                "steps": [],
            }
            state.chains[chain_id] = chain
            self._send_json(202, {"chain": chain, "jobs": []})
            return
        self._problem(404, "not_found", "Unknown path.")


@pytest.fixture()
def fake_server() -> Any:
    _FakeMuse4AIHandler.state = _FakeState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeMuse4AIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _client(base_url: str, key: str | None = SECRET) -> Muse4AIClient:
    return Muse4AIClient(base_url=base_url, api_key=key, request_timeout=5.0)


def _registry(base_url: str, *, key: str | None = SECRET, timeout: float = 5.0) -> ToolRegistry:
    registry = ToolRegistry()
    register_media_tools(registry, _client(base_url, key), timeout=timeout, poll_interval=0.01)
    return registry


def _closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


# -- happy paths -------------------------------------------------------------


def test_status_reports_running_app_and_accounts(fake_server: str) -> None:
    registry = _registry(fake_server)
    result = registry.call("media_status", {})
    assert "running" in result
    assert "main" in result
    assert "muse.video.extend" in result
    assert SECRET not in result


def test_generate_image_polls_to_completion(fake_server: str) -> None:
    registry = _registry(fake_server)
    result = registry.call("media_generate_image", {"prompt": "a lighthouse at dawn"})
    assert "succeeded" in result
    assert "job-1" in result
    assert "asset-job-1" in result
    assert "http://127.0.0.1/dl/job-1" in result
    assert SECRET not in result


def test_generate_video_polls_to_completion(fake_server: str) -> None:
    registry = _registry(fake_server)
    result = registry.call("media_generate_video", {"prompt": "waves on a beach"})
    assert "succeeded" in result
    assert "asset-job-1" in result
    assert "mc_fake_conversation" in result
    assert SECRET not in result


def test_list_and_get_job(fake_server: str) -> None:
    registry = _registry(fake_server)
    registry.call("media_generate_image", {"prompt": "a lighthouse at dawn"})
    listing = registry.call("media_list_jobs", {})
    assert "job-1" in listing
    assert "succeeded" in listing
    detail = registry.call("media_get_job", {"job_id": "job-1"})
    assert "asset-job-1" in detail
    assert SECRET not in listing + detail


def test_extend_video_polls_the_chain_to_completion(fake_server: str) -> None:
    registry = _registry(fake_server)
    registry.call("media_generate_video", {"prompt": "waves on a beach"})
    result = registry.call("media_extend_video", {"asset_id": "asset-job-1"})
    assert "completed" in result
    assert "asset-chain-" in result
    assert SECRET not in result


# -- honest failures -----------------------------------------------------------


def test_failed_job_is_reported_as_failed_never_as_success(fake_server: str) -> None:
    registry = _registry(fake_server)
    result = registry.call("media_generate_video", {"prompt": "please fail this"})
    assert "FAILED" in result
    assert "PROVIDER_ERROR" in result
    assert "succeeded" not in result


def test_timeout_reports_still_running_with_the_job_id(fake_server: str) -> None:
    registry = _registry(fake_server, timeout=0.05)
    result = registry.call("media_generate_image", {"prompt": "a shot that never finishes"})
    assert "still running" in result
    assert "job-1" in result
    assert "succeeded" not in result


def test_extend_unknown_asset_is_an_honest_404(fake_server: str) -> None:
    registry = _registry(fake_server)
    with pytest.raises(ToolError, match="404"):
        registry.call("media_extend_video", {"asset_id": "asset-nope"})


def test_wrong_key_gets_the_401_explanation_and_leaks_nothing(fake_server: str) -> None:
    registry = _registry(fake_server, key="msk_wrong_key")
    with pytest.raises(ToolError, match="rejected the API key"):
        registry.call("media_list_jobs", {})


def test_unreachable_server_is_reported_plainly() -> None:
    base_url = f"http://127.0.0.1:{_closed_port()}"
    registry = _registry(base_url)
    status = registry.call("media_status", {})
    assert "NOT available" in status
    assert "not reachable" in status
    with pytest.raises(ToolError, match="not reachable"):
        registry.call("media_generate_image", {"prompt": "anything"})
    with pytest.raises(MediaError, match="not reachable"):
        _client(base_url).health()


def test_no_key_configured_explains_what_to_set(fake_server: str) -> None:
    registry = _registry(fake_server, key=None)
    with pytest.raises(ToolError, match="MAJORDOMO_MUSE4AI_KEY"):
        registry.call("media_generate_image", {"prompt": "anything"})
    with pytest.raises(ToolError, match="MAJORDOMO_MUSE4AI_KEY"):
        registry.call("media_list_jobs", {})
    # Status still works without a key: health needs none.
    status = registry.call("media_status", {})
    assert "health OK" in status
    assert "MAJORDOMO_MUSE4AI_KEY" in status


def test_the_key_never_appears_in_any_output(fake_server: str) -> None:
    registry = _registry(fake_server)
    outputs = [
        registry.call("media_status", {}),
        registry.call("media_generate_image", {"prompt": "a lighthouse"}),
        registry.call("media_list_jobs", {}),
        registry.call("media_get_job", {"job_id": "job-1"}),
    ]
    # Error path with the real key held by the client: flip what the
    # server expects so the client gets a 401 while carrying SECRET.
    _FakeMuse4AIHandler.state.expected_key = "msk_someone_elses_key"
    with pytest.raises(ToolError) as excinfo:
        registry.call("media_list_jobs", {})
    outputs.append(str(excinfo.value))
    for output in outputs:
        assert SECRET not in output


# -- gate classes, registration, MCP exposure -----------------------------------


def test_tool_risk_classes(fake_server: str) -> None:
    registry = _registry(fake_server)
    for name in ("media_status", "media_list_jobs", "media_get_job"):
        tool = registry.get(name)
        assert tool is not None and tool.read_only, name
    for name in ("media_generate_image", "media_generate_video", "media_extend_video"):
        tool = registry.get(name)
        assert tool is not None and not tool.read_only, name


def test_media_tools_registered_by_default(runtime: Any) -> None:
    names = runtime.registry.names()
    for name in (
        "media_status",
        "media_list_jobs",
        "media_get_job",
        "media_generate_image",
        "media_generate_video",
        "media_extend_video",
    ):
        assert name in names


def test_media_off_removes_the_tools(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", provider="fake", media=False)
    runtime = build_runtime(settings, provider=FakeProvider(), offline=True)
    try:
        assert not any(name.startswith("media_") for name in runtime.registry.names())
    finally:
        runtime.close()


def test_mcp_server_exposes_read_only_media_tools_by_default(runtime: Any) -> None:
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    reply = handle_message(runtime.registry, False, message)
    assert reply is not None
    names = {tool["name"] for tool in reply["result"]["tools"]}
    assert "media_status" in names
    assert "media_list_jobs" in names
    assert "media_generate_image" not in names
    reply = handle_message(runtime.registry, True, message)
    assert reply is not None
    names = {tool["name"] for tool in reply["result"]["tools"]}
    assert "media_generate_image" in names
    assert "media_extend_video" in names


def test_module_has_no_new_dependencies() -> None:
    """media.py is stdlib-only: its imports stay in a small known set."""
    import ast

    tree = ast.parse(Path(media_module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    allowed = {"__future__", "json", "time", "urllib", "collections", "typing"}
    assert imported <= allowed, imported - allowed
