"""Kaydedilecek Streamlit uygulamasını ayrı bir alt süreçte başlatır.

Tur stüdyosunun kendisi de bir Streamlit sayfası olduğu için, kaydı yapılan
uygulama AYRI bir portta AYRI bir süreç olarak çalıştırılır. Böylece ajan
gezinirken stüdyo sayfasının kendi oturum durumu etkilenmez ve iki uygulama
birbirinin `session_state`'ini bozmaz.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_ENTRYPOINT = REPO_ROOT / "app.py"

DEFAULT_STARTUP_TIMEOUT_SECONDS = 60.0
_HEALTH_PATH = "/_stcore/health"


def find_free_port() -> int:
    """İşletim sisteminden boş bir TCP portu ister."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _health_url(port: int) -> str:
    return f"http://127.0.0.1:{port}{_HEALTH_PATH}"


def wait_until_healthy(port: int, timeout_seconds: float = DEFAULT_STARTUP_TIMEOUT_SECONDS) -> bool:
    """Streamlit sağlık uç noktası yanıt verene kadar bekler."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(_health_url(port), timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.4)
    return False


def build_launch_command(port: int, entrypoint: Path = APP_ENTRYPOINT) -> list:
    """Streamlit'i başlatan komutu kurar (test edilebilir olsun diye ayrı)."""
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(entrypoint),
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "true",
        # Kayıt sırasında "yeni sürüm var" gibi kutular videoya girmesin.
        "--global.developmentMode",
        "false",
        "--browser.gatherUsageStats",
        "false",
        "--client.toolbarMode",
        "minimal",
    ]


class StreamlitAppServer:
    """Kaydedilecek uygulamayı yöneten basit süreç sarmalayıcısı."""

    def __init__(self, port: Optional[int] = None, entrypoint: Path = APP_ENTRYPOINT):
        self.port = port or find_free_port()
        self.entrypoint = entrypoint
        self.process: Optional[subprocess.Popen] = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout_seconds: float = DEFAULT_STARTUP_TIMEOUT_SECONDS) -> None:
        env = dict(os.environ)
        # Alt uygulamanın kendi oturum dosyalarını ana uygulamayla karıştırmaması
        # için Streamlit'in gözetleme/telemetri davranışını kapatıyoruz.
        env["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
        env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

        self.process = subprocess.Popen(
            build_launch_command(self.port, self.entrypoint),
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        if not wait_until_healthy(self.port, timeout_seconds):
            stderr_output = ""
            if self.process and self.process.stderr:
                try:
                    self.process.stderr.close()
                except Exception:  # noqa: BLE001
                    pass
            self.stop()
            raise RuntimeError(
                f"Streamlit uygulaması {timeout_seconds:.0f} saniye içinde {self.port} "
                f"portunda başlatılamadı. {stderr_output}".strip()
            )

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None


@contextmanager
def running_app(port: Optional[int] = None, entrypoint: Path = APP_ENTRYPOINT):
    """Uygulamayı başlatan/durduran context manager."""
    server = StreamlitAppServer(port=port, entrypoint=entrypoint)
    server.start()
    try:
        yield server
    finally:
        server.stop()
