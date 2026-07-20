from __future__ import annotations

import asyncio
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


MODULE_DIR = Path(__file__).parents[1] / "custom_components" / "lx_opensubsonic"
sys.path.insert(0, str(MODULE_DIR))
import lx_js_runner as module  # noqa: E402
import music_backend  # noqa: E402


SCRIPT = r"""
const { EVENT_NAMES, on, send } = globalThis.lx
on(EVENT_NAMES.request, ({ source, action, info }) => {
  if (action !== 'musicUrl') throw new Error('unsupported action')
  return `https://1.1.1.1/${source}/${info.musicInfo.songmid}?q=${info.type}`
})
send(EVENT_NAMES.inited, { sources: {} })
"""


def resolve(script: str) -> str:
    return asyncio.run(
        module.resolve_lx_music_url(
            script=script,
            source="tx",
            songmid="abc123",
            quality="320k",
            timeout=5,
        )
    )


def test_resolve_music_url_from_lx_plugin() -> None:
    assert resolve(SCRIPT) == "https://1.1.1.1/tx/abc123?q=320k"


def test_rejects_non_http_result() -> None:
    assert resolve("globalThis.lx.on('request', () => 'file:///etc/passwd')") == ""


def test_rejects_private_network_result() -> None:
    assert resolve("globalThis.lx.on('request', () => 'http://127.0.0.1/private')") == ""


def test_js_runtime_has_no_python_or_browser_bridge() -> None:
    script = r"""
const { EVENT_NAMES, on } = globalThis.lx
on(EVENT_NAMES.request, () => {
  if (typeof globalThis.python !== 'undefined') return 'https://1.1.1.1/leaked-python'
  if (typeof globalThis.XMLHttpRequest !== 'undefined') return 'https://1.1.1.1/leaked-xhr'
  if (typeof globalThis.setTimeout !== 'undefined') return 'https://1.1.1.1/leaked-timer'
  return 'https://1.1.1.1/sandboxed'
})
"""
    assert resolve(script) == "https://1.1.1.1/sandboxed"


def test_runner_returns_empty_when_concurrency_limit_is_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_RUNNER_SEMAPHORE", threading.BoundedSemaphore(0))
    assert module._resolve_in_process(SCRIPT, "tx", "abc123", "320k", 5) == ""


class _RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1/private")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def test_lx_request_rejects_redirect_to_private_network(monkeypatch: pytest.MonkeyPatch) -> None:
    server = HTTPServer(("127.0.0.1", 0), _RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def fake_resolve_public_ips(hostname: str, port: int) -> list[str]:
        if hostname == "example.com":
            return ["127.0.0.1"]
        raise ValueError("blocked")

    monkeypatch.setattr(module, "_resolve_public_ips", fake_resolve_public_ips)
    try:
        with pytest.raises(ValueError):
            module._http_request(f"http://example.com:{server.server_port}/start", "{}")
    finally:
        server.shutdown()
        server.server_close()


class _FakeContent:
    async def iter_chunked(self, size: int):
        yield b"x" * (music_backend.MAX_MUSIC_SOURCE_JS_BYTES + 1)


class _FakeResponse:
    charset = "utf-8"
    content = _FakeContent()


def test_music_source_js_download_is_size_limited() -> None:
    with pytest.raises(ValueError, match="too large"):
        asyncio.run(music_backend._read_limited_text(_FakeResponse()))
