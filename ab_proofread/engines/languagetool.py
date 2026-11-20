"""Local LanguageTool HTTP client and optional Java service manager.

Requires a separately obtained LanguageTool standalone JAR and Java runtime.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import time
import socket
import threading
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from ..core import Suggestion, parse_matches

class LanguageToolError(RuntimeError): pass

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LanguageToolError("LanguageTool redirects are refused")

class LTClient:
    MAX_INPUT = 1_000_000
    MAX_RESPONSE = 8_000_000
    def __init__(self, base_url: str = "http://127.0.0.1:18081", timeout: float = 8.0, dictionary_exclusions=()):
        parts = urlsplit(base_url)
        if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost", "::1") or parts.username or parts.password or parts.path not in ("", "/") or parts.query or parts.fragment:
            raise ValueError("LanguageTool URL must be plain HTTP on loopback")
        host = '[::1]' if parts.hostname == '::1' else '127.0.0.1'
        self.base_url = f"http://{host}:{parts.port or 80}"
        self.timeout, self.dictionary_exclusions = timeout, tuple(dictionary_exclusions)
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())
    def check(self, text: str, language: str) -> list[Suggestion]:
        if not isinstance(text, str) or len(text.encode("utf-8")) > self.MAX_INPUT: raise ValueError("text exceeds input limit")
        if not isinstance(language, str) or not language or len(language) > 40: raise ValueError("invalid language")
        body = urlencode({"text": text, "language": language}).encode("utf-8")
        request = Request(self.base_url + "/v2/check", data=body, headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8", "Accept": "application/json"}, method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                if response.status != 200: raise LanguageToolError(f"LanguageTool returned HTTP {response.status}")
                raw = response.read(self.MAX_RESPONSE + 1)
            if len(raw) > self.MAX_RESPONSE: raise LanguageToolError("LanguageTool response exceeds limit")
            payload = json.loads(raw.decode("utf-8"))
            return parse_matches(text, payload, self.dictionary_exclusions)
        except LanguageToolError: raise
        except Exception as exc:
            raise LanguageToolError(f"LanguageTool check failed: {exc}") from exc

class LTService:
    """Start/stop only the Java child created by this instance."""
    def __init__(self, jar_path, port: int = 18081, java: str = "java", startup_timeout: float = 30.0):
        self.jar_path = Path(jar_path).expanduser().resolve()
        if not self.jar_path.is_file(): raise FileNotFoundError(self.jar_path)
        if not 1 <= port <= 65535: raise ValueError("invalid port")
        self.port, self.java, self.startup_timeout = port, java, startup_timeout
        self.process = None
        self._lock = threading.RLock()
        self._closed = False
    def ensure_running(self):
        with self._lock:
            return self._ensure_running()
    def _ensure_running(self):
        if self._closed: raise LanguageToolError('LanguageTool manager is closed')
        if self.process is not None and self.process.poll() is None: return
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', self.port))
            except OSError as exc:
                raise LanguageToolError('LanguageTool port is already occupied') from exc
        command = [self.java, "-Xmx768m", "-cp", str(self.jar_path), "org.languagetool.server.HTTPServer", "--port", str(self.port)]
        try: self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, shell=False)
        except OSError as exc: raise LanguageToolError(f"cannot start Java LanguageTool service: {exc}") from exc
        client = LTClient(f"http://127.0.0.1:{self.port}", timeout=1)
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None: raise LanguageToolError("LanguageTool service exited during startup")
            try:
                client.check("", "en-US")
                return self
            except LanguageToolError:
                time.sleep(0.15)
        self.stop()
        raise LanguageToolError("LanguageTool service did not become ready")
    def stop(self):
        with self._lock:
            self._closed = True
            process, self.process = self.process, None
            if process is not None and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
    def __enter__(self): return self.ensure_running()
    def __exit__(self, *exc): self.stop()
