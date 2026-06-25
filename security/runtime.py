from __future__ import annotations

import contextlib
import ipaddress
import json
import os
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterator


def configure_offline_environment() -> None:
    """Force optional local-model libraries into offline mode."""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ.setdefault("DO_NOT_TRACK", "1")
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


def _is_local_host(host: str) -> bool:
    if host in {"localhost", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        try:
            return all(ipaddress.ip_address(x[4][0]).is_loopback for x in socket.getaddrinfo(host, None))
        except Exception:
            return False


_NETWORK_GUARD_LOCK = threading.Lock()
_NETWORK_GUARD_COUNT = 0
_ORIGINAL_SOCKET_CONNECT = socket.socket.connect
_ORIGINAL_CREATE_CONNECTION = socket.create_connection


def _guarded_connect(sock, address):
    host = address[0] if isinstance(address, tuple) else str(address)
    if not _is_local_host(str(host)):
        raise PermissionError(f"Strict privacy blocked external network connection to {host}")
    return _ORIGINAL_SOCKET_CONNECT(sock, address)


def _guarded_create(address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else str(address)
    if not _is_local_host(str(host)):
        raise PermissionError(f"Strict privacy blocked external network connection to {host}")
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


@contextlib.contextmanager
def deny_external_network(enabled: bool = True) -> Iterator[None]:
    """Best-effort process-level egress guard with concurrent-job safety.

    The socket patch is reference-counted so one worker cannot restore network
    access while another protected worker is still running. Loopback remains
    available for local services.
    """
    global _NETWORK_GUARD_COUNT
    if not enabled:
        yield
        return

    with _NETWORK_GUARD_LOCK:
        if _NETWORK_GUARD_COUNT == 0:
            socket.socket.connect = _guarded_connect
            socket.create_connection = _guarded_create
        _NETWORK_GUARD_COUNT += 1
    try:
        yield
    finally:
        with _NETWORK_GUARD_LOCK:
            _NETWORK_GUARD_COUNT = max(0, _NETWORK_GUARD_COUNT - 1)
            if _NETWORK_GUARD_COUNT == 0:
                socket.socket.connect = _ORIGINAL_SOCKET_CONNECT
                socket.create_connection = _ORIGINAL_CREATE_CONNECTION


@contextlib.contextmanager
def secure_workspace(prefix: str = "hsmt_") -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        try:
            os.chmod(root, 0o700)
        except Exception:
            pass
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def append_audit_event(log_path: str | Path, event: dict) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **event}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
