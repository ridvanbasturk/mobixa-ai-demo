"""Kaydedilecek uygulamayı başlatan katmanın testleri.

Gerçek bir Streamlit süreci BAŞLATILMAZ; yalnızca komut kurulumu, port
seçimi ve sağlık kontrolünün zaman aşımı davranışı test edilir.
"""
from __future__ import annotations

import socket
from pathlib import Path

from services.tour_app_server import (
    APP_ENTRYPOINT,
    StreamlitAppServer,
    build_launch_command,
    find_free_port,
    wait_until_healthy,
)


def test_find_free_port_returns_a_bindable_port():
    port = find_free_port()
    assert 1024 < port < 65536
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))  # gerçekten boş olmalı


def test_launch_command_targets_the_real_app_entrypoint():
    command = build_launch_command(8599)
    assert "streamlit" in command
    assert "run" in command
    assert str(APP_ENTRYPOINT) in command
    assert command[command.index("--server.port") + 1] == "8599"


def test_launch_command_is_headless_and_quiet():
    # Kayıt sırasında tarayıcı kendiliğinden açılmamalı ve telemetri/araç
    # çubuğu kutuları videoya girmemeli.
    command = build_launch_command(1234)
    assert command[command.index("--server.headless") + 1] == "true"
    assert command[command.index("--browser.gatherUsageStats") + 1] == "false"
    assert command[command.index("--client.toolbarMode") + 1] == "minimal"


def test_launch_command_binds_to_loopback_only():
    command = build_launch_command(1234)
    assert command[command.index("--server.address") + 1] == "127.0.0.1"


def test_launch_command_accepts_custom_entrypoint(tmp_path):
    entry = tmp_path / "other_app.py"
    command = build_launch_command(4321, entrypoint=entry)
    assert str(entry) in command


def test_wait_until_healthy_returns_false_on_dead_port():
    dead_port = find_free_port()  # kimse dinlemiyor
    assert wait_until_healthy(dead_port, timeout_seconds=1.0) is False


def test_server_base_url_uses_loopback():
    server = StreamlitAppServer(port=9123)
    assert server.base_url == "http://127.0.0.1:9123"


def test_stop_is_safe_when_never_started():
    StreamlitAppServer(port=9124).stop()  # istisna fırlatmamalı


def test_app_entrypoint_exists():
    assert Path(APP_ENTRYPOINT).exists()
