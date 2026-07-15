from __future__ import annotations

import asyncio
import sys
from pathlib import Path


MODULE_DIR = Path(__file__).parents[1] / "custom_components" / "lx_opensubsonic"
sys.path.insert(0, str(MODULE_DIR))
import lx_js_runner as module  # noqa: E402


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
