import socket
import pytest

from security.runtime import deny_external_network


def test_network_guard_blocks_external():
    with deny_external_network(True):
        s = socket.socket()
        with pytest.raises(PermissionError):
            s.connect(("8.8.8.8", 53))
        s.close()
