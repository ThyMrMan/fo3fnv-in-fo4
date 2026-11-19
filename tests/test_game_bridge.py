"""The bridge client against a real named pipe: a game that never answers fails the request in time."""
import ctypes
import time

import pytest

from tools.live.game_bridge import Bridge, BridgeError

PIPE = r'\\.\pipe\f3nv_test_silent'
#: CreateNamedPipeW: duplex, byte mode, one instance, 4 KB buffers.
PIPE_ACCESS_DUPLEX, PIPE_TYPE_BYTE, INVALID_HANDLE = 3, 0, ctypes.c_void_p(-1).value


@pytest.fixture
def silent_game():
    """A pipe server that accepts the client and never replies."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateNamedPipeW.restype = ctypes.c_void_p
    handle = kernel32.CreateNamedPipeW(PIPE, PIPE_ACCESS_DUPLEX, PIPE_TYPE_BYTE, 1, 4096, 4096, 0, None)
    assert handle != INVALID_HANDLE
    yield
    kernel32.CloseHandle(ctypes.c_void_p(handle))


def test_a_hung_game_fails_the_request_after_the_timeout(silent_game):
    """No reply: E_TIMEOUT after `timeout` seconds, not a wait forever."""
    bridge = Bridge(pipe=PIPE, timeout=0.5, loading_retries=1).connect()
    began = time.time()
    with pytest.raises(BridgeError) as err:
        bridge.status()
    assert err.value.code == 'E_TIMEOUT' and time.time() - began < 5
