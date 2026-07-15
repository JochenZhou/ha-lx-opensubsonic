"""Isolated JavaScript runner for explicitly trusted LX source plugins.

The worker uses QuickJS without exposing Python, Home Assistant, filesystem,
process, or environment APIs. Only the restricted lx.on/send/request API is
exposed. The plugin
still executes code and can access public HTTP(S) endpoints, so this feature is
strictly opt-in and carries user-accepted risk.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import multiprocessing
import socket
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

_MAX_SCRIPT_BYTES = 1024 * 1024
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only HTTP(S) requests are allowed")
    for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)):
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError("Private, local, reserved, and non-global network targets are blocked")


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _http_request(url: str, options_json: str) -> str:
    _validate_public_http_url(url)
    options = json.loads(options_json or "{}")
    method = str(options.get("method") or "GET").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
        raise ValueError("Unsupported HTTP method")
    headers = {str(k): str(v) for k, v in (options.get("headers") or {}).items()}
    body = options.get("body", options.get("data"))
    if isinstance(body, (dict, list)):
        body = json.dumps(body, ensure_ascii=False)
        headers.setdefault("Content-Type", "application/json")
    payload = str(body).encode("utf-8") if body is not None else None
    timeout = max(1.0, min(float(options.get("timeout") or 10000) / 1000.0, 20.0))
    req = Request(url, data=payload, headers=headers, method=method)
    opener = build_opener(_SafeRedirectHandler())
    with opener.open(req, timeout=timeout) as response:
        content = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(content) > _MAX_RESPONSE_BYTES:
            raise ValueError("HTTP response is too large")
        return json.dumps(
            {
                "statusCode": response.status,
                "headers": dict(response.headers.items()),
                "body": content.decode("utf-8", errors="replace"),
            },
            ensure_ascii=False,
        )


def _resolve_sync(script: str, source: str, songmid: str, quality: str) -> str:
    if not script or len(script.encode("utf-8")) > _MAX_SCRIPT_BYTES:
        return ""
    import quickjs

    context = quickjs.Context()
    context.set_memory_limit(64 * 1024 * 1024)
    context.set_max_stack_size(1024 * 1024)
    context.add_callable("__py_http_request", _http_request)
    bootstrap = r"""
const __lxHandlers = Object.create(null)
globalThis.console = { log() {}, warn() {}, error() {}, info() {}, debug() {} }
globalThis.lx = {
  EVENT_NAMES: { request: 'request', inited: 'inited' },
  on(name, handler) { __lxHandlers[name] = handler },
  send(name, data) { return undefined },
  request(url, options, callback) {
    if (typeof options === 'function') {
      callback = options
      options = {}
    }
    options = options || {}
    try {
      const response = JSON.parse(__py_http_request(String(url), JSON.stringify(options)))
      if (typeof callback === 'function') callback(null, response, response.body)
      return Promise.resolve(response)
    } catch (error) {
      if (typeof callback === 'function') callback(error)
      return Promise.reject(new Error(String(error)))
    }
  },
}
globalThis.__lxResult = { done: false, value: '', error: '' }
globalThis.__lxStart = function(payloadJson) {
  const handler = __lxHandlers.request
  if (typeof handler !== 'function') {
    __lxResult = { done: true, value: '', error: 'request handler not registered' }
    return
  }
  try {
    Promise.resolve(handler(JSON.parse(payloadJson))).then(
      value => { __lxResult = { done: true, value: typeof value === 'string' ? value : '', error: '' } },
      error => { __lxResult = { done: true, value: '', error: String(error) } },
    )
  } catch (error) {
    __lxResult = { done: true, value: '', error: String(error) }
  }
}
"""
    context.eval(bootstrap)
    context.eval(script)
    payload = json.dumps(
        {
            "action": "musicUrl",
            "source": source,
            "info": {
                "type": quality,
                "musicInfo": {"songmid": songmid, "hash": songmid, "musicId": songmid},
            },
        },
        ensure_ascii=False,
    )
    context.eval(f"__lxStart({json.dumps(payload)})")
    for _ in range(10000):
        state = json.loads(context.eval("JSON.stringify(__lxResult)"))
        if state.get("done"):
            value = state.get("value")
            break
        if not context.execute_pending_job():
            return ""
    else:
        return ""
    if not isinstance(value, str):
        return ""
    try:
        _validate_public_http_url(value)
    except (OSError, ValueError):
        return ""
    return value


def _worker(connection, script: str, source: str, songmid: str, quality: str) -> None:
    try:
        value = _resolve_sync(script, source, songmid, quality)
        connection.send((True, value))
    except BaseException as err:
        connection.send((False, str(err)))
    finally:
        connection.close()


def _resolve_in_process(script: str, source: str, songmid: str, quality: str, timeout: float) -> str:
    ctx = multiprocessing.get_context("spawn")
    receive_connection, send_connection = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_worker,
        args=(send_connection, script, source, songmid, quality),
        daemon=True,
    )
    process.start()
    send_connection.close()
    process.join(timeout=max(1.0, min(float(timeout), 20.0)))
    if process.is_alive():
        process.terminate()
        process.join(2)
        receive_connection.close()
        return ""
    if not receive_connection.poll(0.5):
        receive_connection.close()
        return ""
    ok, value = receive_connection.recv()
    receive_connection.close()
    if not ok:
        raise RuntimeError(f"LX JS 子进程执行失败: {value}")
    return str(value)


async def resolve_lx_music_url(
    *, script: str, source: str, songmid: str, quality: str, timeout: float = 10
) -> str:
    """Execute one opt-in LX plugin request in an isolated JS process."""
    return await asyncio.wait_for(
        asyncio.to_thread(_resolve_in_process, script, source, songmid, quality, timeout),
        timeout=max(1.0, min(float(timeout), 20.0)) + 3,
    )
