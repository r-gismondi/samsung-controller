"""One TCP session per panel.

Unknown device ids are found by a power query over ids 0–10. A timeout while
probing means that id did not answer. A timeout or a closed socket after the
id is known means the panel is offline. A NAK is returned to the caller with
no retry.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from typing import Protocol

from samsung_controller.protocol import (
    CMD_INPUT,
    CMD_MANUAL_LAMP,
    CMD_MODEL_NAME,
    CMD_PANEL_ON_OFF,
    CMD_POWER,
    CMD_SAFETY_LOCK,
    CMD_SCREEN_SIZE,
    CMD_STATUS,
    CMD_VIDEO_WALL_LAYOUT,
    CMD_VIDEO_WALL_MODE,
    CMD_VIDEO_WALL_ON,
    CMD_VOLUME,
    POWER_SETTLE_SECONDS,
    PROBE_IDS,
    BadFrame,
    CommandRejected,
    ConnectionClosed,
    DeviceIdNotFound,
    MdcError,
    PanelOffline,
    PanelSettling,
    PanelStatus,
    Response,
    ResponseTimeout,
    encode,
    parse,
    parse_model_name,
    parse_status,
    require_input,
    require_percent,
    wall_div,
)

Clock = Callable[[], float]
POWER_COMMANDS = frozenset({CMD_POWER})


class Transport(Protocol):
    def sendall(self, data: bytes) -> None: ...

    def recv_exact(self, size: int) -> bytes: ...

    def close(self) -> None: ...


class SocketTransport:
    def __init__(self, sock: socket.socket):
        self._sock = sock

    def sendall(self, data: bytes) -> None:
        try:
            self._sock.sendall(data)
        except TimeoutError as exc:
            raise ResponseTimeout("send timed out") from exc
        except OSError as exc:
            raise ConnectionClosed("send failed") from exc

    def recv_exact(self, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            try:
                chunk = self._sock.recv(size - len(chunks))
            except TimeoutError as exc:
                raise ResponseTimeout("read timed out") from exc
            except OSError as exc:
                raise ConnectionClosed("read failed") from exc
            if not chunk:
                raise ConnectionClosed("connection closed")
            chunks += chunk
        return bytes(chunks)

    def close(self) -> None:
        self._sock.close()


def open_connection(host: str, port: int, timeout: float, attempts: int = 1) -> socket.socket:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    last: OSError | None = None
    for _ in range(attempts):
        try:
            sock = socket.create_connection((host, port), timeout)
        except OSError as exc:
            last = exc
            continue
        sock.settimeout(timeout)
        return sock
    raise PanelOffline(f"could not connect to {host}:{port}") from last


def read_frame(transport: Transport) -> bytes:
    try:
        head = transport.recv_exact(4)
    except (ResponseTimeout, ConnectionClosed):
        raise
    except OSError as exc:
        raise ConnectionClosed("read failed") from exc
    if len(head) != 4 or head[0] != 0xAA:
        raise BadFrame("response did not start with 0xAA")
    try:
        tail = transport.recv_exact(head[3] + 1)
    except (ResponseTimeout, ConnectionClosed):
        raise
    return head + tail


class Session:
    def __init__(
        self,
        transport: Transport,
        device_id: int | None = None,
        clock: Clock | None = None,
        settle_seconds: float = POWER_SETTLE_SECONDS,
    ):
        self.transport = transport
        self.device_id = device_id
        self.clock = clock or time.monotonic
        self.settle_seconds = settle_seconds
        self.ready_at: float | None = None

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def probe(self) -> int:
        """Return the first id in 0–10 whose power query ACKs."""
        for device_id in PROBE_IDS:
            try:
                response = self._exchange(device_id, CMD_POWER, b"")
            except ResponseTimeout:
                continue
            except ConnectionClosed as exc:
                raise PanelOffline("connection closed while probing the device id") from exc
            except BadFrame as exc:
                raise BadFrame("device id probe received a bad frame") from exc
            if response.device_id != device_id:
                raise BadFrame("response device id does not match the probe")
            if response.ack and response.command == CMD_POWER:
                self.device_id = device_id
                return device_id
        raise DeviceIdNotFound("no device id from 0 to 10 ACKed a power query")

    def request(self, command: int, data: bytes = b"", now: float | None = None) -> Response:
        if self.device_id is None:
            raise DeviceIdNotFound("probe the device id before sending a command")
        moment = self.clock() if now is None else now
        self._ensure_ready(moment)
        try:
            response = self._exchange(self.device_id, command, data)
        except ResponseTimeout as exc:
            raise PanelOffline("panel did not answer") from exc
        except ConnectionClosed as exc:
            raise PanelOffline("connection closed") from exc
        if response.device_id != self.device_id:
            raise BadFrame("response device id does not match the request")
        if not response.ack:
            raise CommandRejected(response.command, response.error_code or 0)
        if response.command != command:
            raise BadFrame("response command does not match the request")
        if command in POWER_COMMANDS and data:
            self.ready_at = moment + self.settle_seconds
        return response

    def get_power(self) -> int:
        return _single_byte(self.request(CMD_POWER), "power")

    def set_power(self, on: bool, now: float | None = None) -> None:
        self.request(CMD_POWER, bytes((1 if on else 0,)), now=now)

    def get_volume(self) -> int:
        return _single_byte(self.request(CMD_VOLUME), "volume")

    def set_volume(self, level: int) -> None:
        self.request(CMD_VOLUME, bytes((require_percent(level, "volume"),)))

    def get_input(self) -> int:
        return _single_byte(self.request(CMD_INPUT), "input")

    def set_input(self, source: int) -> None:
        self.request(CMD_INPUT, bytes((require_input(source),)))

    def get_backlight(self) -> int:
        return _single_byte(self.request(CMD_MANUAL_LAMP), "backlight")

    def set_backlight(self, level: int) -> None:
        self.request(CMD_MANUAL_LAMP, bytes((require_percent(level, "backlight"),)))

    def get_panel_power(self) -> int:
        return _single_byte(self.request(CMD_PANEL_ON_OFF), "panel power")

    def set_panel_power(self, on: bool) -> None:
        self.request(CMD_PANEL_ON_OFF, bytes((1 if on else 0,)))

    def get_status(self) -> PanelStatus:
        return parse_status(self.request(CMD_STATUS).data)

    def get_model_name(self) -> str:
        return parse_model_name(self.request(CMD_MODEL_NAME).data)

    def get_screen_size(self) -> int:
        return _single_byte(self.request(CMD_SCREEN_SIZE), "screen size")

    def set_screen_size(self, size: int) -> None:
        if not 0 <= size <= 0xFF:
            raise ValueError("screen size must be 0–255")
        self.request(CMD_SCREEN_SIZE, bytes((size,)))

    def set_video_wall_enabled(self, on: bool) -> None:
        self.request(CMD_VIDEO_WALL_ON, bytes((1 if on else 0,)))

    def set_video_wall_mode(self, mode: int) -> None:
        if not 0 <= mode <= 0xFF:
            raise ValueError("video wall mode must be 0–255")
        self.request(CMD_VIDEO_WALL_MODE, bytes((mode,)))

    def set_video_wall_layout(self, rows: int, cols: int, index: int) -> None:
        if not 1 <= index <= rows * cols:
            raise ValueError("screen index is outside the wall")
        self.request(CMD_VIDEO_WALL_LAYOUT, bytes((wall_div(rows, cols), index)))

    def set_safety_lock(self, locked: bool) -> None:
        self.request(CMD_SAFETY_LOCK, bytes((1 if locked else 0,)))

    def _ensure_ready(self, now: float) -> None:
        if self.ready_at is not None and now < self.ready_at:
            raise PanelSettling(self.ready_at - now)

    def _exchange(self, device_id: int, command: int, data: bytes) -> Response:
        self.transport.sendall(encode(command, device_id, data))
        return parse(read_frame(self.transport))


def _single_byte(response: Response, label: str) -> int:
    if len(response.data) != 1:
        raise BadFrame(f"{label} payload is not one byte")
    return response.data[0]


__all__ = [
    "MdcError",
    "Session",
    "SocketTransport",
    "open_connection",
]
