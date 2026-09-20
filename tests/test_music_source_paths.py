"""回归测试：音源脚本的 API 路径。

音源脚本用 `${API_URL}/music/url`，早期实现把路径写死成 `/url` 导致 404。
这里锁定两件事：
1. parse_music_source_js 能从各种写法里提取出正确的 base（不能被 /music/url 带偏）
2. resolve_music_url_api 优先走 /music/url，只有 404 时才回退 /url
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

MODULE_DIR = Path(__file__).parents[1] / "custom_components" / "lx_opensubsonic"
sys.path.insert(0, str(MODULE_DIR))
import music_backend  # noqa: E402


# ---------- 1. 解析 ----------

def test_parse_api_url_from_const() -> None:
    script = 'const API_URL = "https://source.example.com/api";\n'
    out = music_backend.parse_music_source_js(script)
    assert out["api_url"] == "https://source.example.com/api"


def test_parse_api_url_strips_trailing_slash() -> None:
    script = 'const API_URL = "https://source.example.com/api/";\n'
    assert music_backend.parse_music_source_js(script)["api_url"] == "https://source.example.com/api"


def test_parse_fallback_music_url_path() -> None:
    """没有 API_URL 常量时，从 .../music/url 反推 base —— 必须剥掉 /music/url。"""
    script = 'const u = "https://source.example.com/api/music/url";\n'
    out = music_backend.parse_music_source_js(script)
    assert out["api_url"] == "https://source.example.com/api"


def test_parse_fallback_plain_url_path() -> None:
    """旧式 .../url 也要能反推 base（回退兼容）。"""
    script = 'const u = "https://old.example.com/api/url";\n'
    out = music_backend.parse_music_source_js(script)
    assert out["api_url"] == "https://old.example.com/api"


def test_parse_real_lx_script_shape() -> None:
    """真实聆澜脚本的关键行：API_URL + 模板串。"""
    script = (
        'const API_URL = "https://source.example.com/api";\n'
        'const API_KEY = "CERU_KEY-ABCDEF";\n'
        "const requestUrl = `${API_URL}/music/url?source=${source}`;\n"
    )
    out = music_backend.parse_music_source_js(script)
    assert out["api_url"] == "https://source.example.com/api"
    assert out["api_key"] == "CERU_KEY-ABCDEF"


# ---------- 2. 请求路径优先级 ----------

class _FakeJsonResponse:
    def __init__(self, status: int, payload: dict[str, Any] | None = None) -> None:
        self.status = status
        self._payload = payload or {}
        self.headers: dict[str, str] = {}

    async def json(self, content_type: Any = None) -> dict[str, Any]:
        return self._payload

    async def __aenter__(self) -> "_FakeJsonResponse":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakeSession:
    """记录被请求的路径，按预设返回 404 或 200。"""

    def __init__(self, ok_paths: set[str]) -> None:
        self.ok_paths = ok_paths
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: Any) -> _FakeJsonResponse:
        self.calls.append(url)
        path = "/" + url.split("://", 1)[1].split("/", 1)[1]
        if path in self.ok_paths:
            return _FakeJsonResponse(200, {"code": 200, "url": f"https://cdn.example.com{path}"})
        return _FakeJsonResponse(404, {"code": 404, "message": f"Cannot GET {path}"})


def _make_backend(session: _FakeSession) -> music_backend.MusicBackend:
    """构造 backend，并用一个已缓存的 JS 抓取结果短路 _ensure_music_source_from_js。"""
    backend = music_backend.MusicBackend(session, search_source="kw")
    backend._source_cache = {
        "url": None,  # 与 music_source_js_url 不同 → 会走网络；所以下面直接打桩
        "api_url": "https://source.example.com/api",
        "api_key": "K",
        "script": "",
        "ts": 0,
    }

    async def _fake_ensure() -> tuple[str, str]:
        return "https://source.example.com/api", "K"

    backend._ensure_music_source_from_js = _fake_ensure  # type: ignore[method-assign]
    return backend


def _song() -> music_backend.Song:
    return music_backend.Song(id="kw_228908", title="t", artist="a", source="kw", songmid="228908")


def test_prefers_music_url_path() -> None:
    """服务端只有 /music/url 时，必须用 /music/url 成功拿到地址（原 bug 的正面场景）。"""
    session = _FakeSession(ok_paths={"/api/music/url"})
    url = asyncio.run(_make_backend(session).resolve_music_url_api(_song()))
    assert url is not None
    assert "/music/url" in session.calls[0]
    assert url.endswith("/api/music/url")


def test_falls_back_to_plain_url_on_404() -> None:
    """服务端只有旧式 /url 时，第一次 404 后要回退并成功。"""
    session = _FakeSession(ok_paths={"/api/url"})
    url = asyncio.run(_make_backend(session).resolve_music_url_api(_song()))
    assert url is not None
    assert any(c.endswith("/api/music/url") for c in session.calls)
    assert any(c.endswith("/api/url") for c in session.calls)


def test_returns_none_when_both_paths_missing() -> None:
    """两条路径都不存在时返回 None（不抛异常）。"""
    session = _FakeSession(ok_paths=set())
    assert asyncio.run(_make_backend(session).resolve_music_url_api(_song())) is None
