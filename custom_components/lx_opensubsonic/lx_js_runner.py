"""Isolated JavaScript runner for explicitly trusted LX source plugins.

The worker uses QuickJS without exposing Python, Home Assistant, filesystem,
process, or environment APIs. Only the restricted lx.on/send/request API is
exposed. The plugin
still executes code and can access public HTTP(S) endpoints, so this feature is
strictly opt-in and carries user-accepted risk.
"""

from __future__ import annotations

import asyncio
import http.client
import ipaddress
import json
import multiprocessing
import os
import resource
import socket
import ssl
import threading
from urllib.parse import urljoin, urlparse

_MAX_SCRIPT_BYTES = 1024 * 1024
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_REDIRECTS = 5
_MAX_CONCURRENT_RUNNERS = 2
_RUNNER_SEMAPHORE = threading.BoundedSemaphore(_MAX_CONCURRENT_RUNNERS)


def _resolve_public_ips(hostname: str, port: int) -> list[str]:
    ips: list[str] = []
    for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError("Private, local, reserved, and non-global network targets are blocked")
        if str(ip) not in ips:
            ips.append(str(ip))
    if not ips:
        raise ValueError("No public address resolved")
    return ips


def _validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only HTTP(S) requests are allowed")
    _resolve_public_ips(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, ip: str, port: int, tls_hostname: str, timeout: float):
        context = ssl.create_default_context()
        super().__init__(ip, port=port, timeout=timeout, context=context)
        self._tls_hostname = tls_hostname
        self._tls_context = context

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), self.timeout, getattr(self, "source_address", None))
        self.sock = self._tls_context.wrap_socket(sock, server_hostname=self._tls_hostname)


def _http_request(url: str, options_json: str) -> str:
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
    current_url = url
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = urlparse(current_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Only HTTP(S) requests are allowed")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        ip = _resolve_public_ips(parsed.hostname, port)[0]
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        request_headers = dict(headers)
        request_headers["Host"] = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
        conn: http.client.HTTPConnection
        if parsed.scheme == "https":
            conn = _PinnedHTTPSConnection(ip, port, parsed.hostname, timeout)
        else:
            conn = http.client.HTTPConnection(ip, port=port, timeout=timeout)
        try:
            conn.request(method, path, body=payload, headers=request_headers)
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                response.read()
                if not location:
                    raise ValueError("Redirect without Location")
                current_url = urljoin(current_url, location)
                _validate_public_http_url(current_url)
                if response.status == 303:
                    method = "GET"
                    payload = None
                continue
            content = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(content) > _MAX_RESPONSE_BYTES:
                raise ValueError("HTTP response is too large")
            return json.dumps(
                {
                    "statusCode": response.status,
                    "headers": dict(response.getheaders()),
                    "body": content.decode("utf-8", errors="replace"),
                },
                ensure_ascii=False,
            )
        finally:
            conn.close()
    raise ValueError("Too many redirects")


def _apply_worker_limits() -> None:
    if os.name != "posix":
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (8, 10))
    except (OSError, ValueError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
    except (OSError, ValueError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    except (OSError, ValueError):
        pass


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
        _apply_worker_limits()
        value = _resolve_sync(script, source, songmid, quality)
        connection.send((True, value))
    except BaseException as err:
        connection.send((False, str(err)))
    finally:
        connection.close()


def _resolve_in_process(script: str, source: str, songmid: str, quality: str, timeout: float) -> str:
    if not _RUNNER_SEMAPHORE.acquire(blocking=False):
        return ""
    try:
        return _resolve_in_process_locked(script, source, songmid, quality, timeout)
    finally:
        _RUNNER_SEMAPHORE.release()


def _resolve_in_process_locked(script: str, source: str, songmid: str, quality: str, timeout: float) -> str:
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
    try:
        ok, value = receive_connection.recv()
    except EOFError:
        receive_connection.close()
        return ""
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
