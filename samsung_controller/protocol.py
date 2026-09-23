"""Samsung Multiple Display Control frames.

A frame is ``AA CMD ID LEN DATA... CHECKSUM``. The checksum is the low byte of
every byte after the header. ``0xFE`` is a serial broadcast and does not ACK,
so it is rejected as a per-panel id.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

HEADER = 0xAA
RESPONSE_COMMAND = 0xFF
ACK = ord("A")
NAK = ord("N")
BROADCAST_ID = 0xFE

CMD_STATUS = 0x00
CMD_POWER = 0x11
CMD_VOLUME = 0x12
CMD_INPUT = 0x14
CMD_SCREEN_SIZE = 0x19
CMD_MANUAL_LAMP = 0x58
CMD_VIDEO_WALL_MODE = 0x5C
CMD_SAFETY_LOCK = 0x5D
CMD_VIDEO_WALL_ON = 0x84
CMD_MODEL_NAME = 0x8A
CMD_VIDEO_WALL_LAYOUT = 0x89
CMD_PANEL_ON_OFF = 0xF9

# General MDC values. A VM55B-U must ACK these before a UI treats them as confirmed.
VIDEO_WALL_MODE_NATURAL = 0x00
VIDEO_WALL_MODE_FULL = 0x01

PROBE_IDS = tuple(range(0, 11))
POWER_SETTLE_SECONDS = 60.0
# The handoff requires a stagger but does not name the gap. Five seconds is a
# starting assumption so the sets do not start on the same instant.
DEFAULT_POWER_STAGGER_SECONDS = 5.0

# This model rejects set-commands for the HDMI-PC source codes.
HDMI_PC_SOURCES = frozenset({0x22, 0x24, 0x32, 0x34})


class InputSource(IntEnum):
    DVI = 0x18
    HDMI1 = 0x21
    HDMI2 = 0x23
    DISPLAY_PORT = 0x25


class MdcError(Exception):
    """Base error for protocol and session failures."""


class BadFrame(MdcError):
    """The bytes are not a valid MDC frame. This is not a panel fault."""


class CommandRejected(MdcError):
    """The panel NACKed the command. Callers must not retry it in a loop."""

    def __init__(self, command: int | None, error_code: int):
        self.command = command
        self.error_code = error_code
        command_text = "unknown" if command is None else f"0x{command:02X}"
        super().__init__(f"NAK for {command_text}, error 0x{error_code:02X}")


class ResponseTimeout(MdcError):
    """The peer did not answer before the read timeout."""


class ConnectionClosed(MdcError):
    """The TCP connection closed before a full frame arrived."""


class DeviceIdNotFound(MdcError):
    """No id in 0–10 ACKed a power query."""


class PanelOffline(MdcError):
    """This panel cannot be reached. Other panels stay independent."""


class PanelSettling(MdcError):
    """A power command on this panel has not finished settling."""

    def __init__(self, remaining_seconds: float):
        self.remaining_seconds = remaining_seconds
        super().__init__(
            f"panel is settling for {remaining_seconds:.1f}s after a power command"
        )


@dataclass(frozen=True)
class Response:
    device_id: int
    ack: bool
    command: int | None
    data: bytes
    error_code: int | None = None


@dataclass(frozen=True)
class PanelStatus:
    power: int
    volume: int
    mute: int
    source: int
    aspect: int
    extra: bytes = b""


def checksum(payload: bytes) -> int:
    return sum(payload) & 0xFF


def encode(command: int, device_id: int, data: bytes = b"") -> bytes:
    if device_id == BROADCAST_ID:
        raise ValueError("0xFE is a broadcast id and does not ACK")
    if not 0 <= device_id <= 0xFD:
        raise ValueError(f"device id {device_id} is outside 0–253")
    if not 0 <= command <= 0xFF:
        raise ValueError(f"command {command} is not a byte")
    if len(data) > 0xFF:
        raise ValueError("MDC data is limited to 255 bytes")
    body = bytes((command, device_id, len(data))) + data
    return bytes((HEADER,)) + body + bytes((checksum(body),))


def parse(frame: bytes) -> Response:
    if len(frame) < 5 or frame[0] != HEADER:
        raise BadFrame("frame is missing the MDC header")
    command, device_id, length = frame[1], frame[2], frame[3]
    if len(frame) != 5 + length:
        raise BadFrame("frame length does not match the length byte")
    if checksum(frame[1:-1]) != frame[-1]:
        raise BadFrame("checksum does not match")
    if command != RESPONSE_COMMAND:
        raise BadFrame("response command is not 0xFF")
    if length < 1:
        raise BadFrame("response has no ACK or NAK byte")
    status = frame[4]
    tail = frame[5:-1]
    if status == ACK:
        if not tail:
            raise BadFrame("ACK is missing the echoed command")
        return Response(device_id, True, tail[0], tail[1:])
    if status == NAK:
        if not tail:
            raise BadFrame("NAK is missing the error byte")
        if len(tail) == 1:
            return Response(device_id, False, None, b"", tail[0])
        return Response(device_id, False, tail[0], tail[2:], tail[1])
    raise BadFrame("response is neither ACK nor NAK")


def parse_status(data: bytes) -> PanelStatus:
    if len(data) < 5:
        raise BadFrame("status payload is shorter than power, volume, mute, input, aspect")
    return PanelStatus(data[0], data[1], data[2], data[3], data[4], data[5:])


def parse_model_name(data: bytes) -> str:
    if not data:
        raise BadFrame("model name payload is empty")
    return data.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


def require_byte(value: int, label: str) -> int:
    if not 0 <= value <= 0xFF:
        raise ValueError(f"{label} must be 0–255")
    return value


def require_percent(value: int, label: str) -> int:
    if not 0 <= value <= 100:
        raise ValueError(f"{label} must be 0–100")
    return value


def require_input(source: int) -> int:
    require_byte(source, "input source")
    if source in HDMI_PC_SOURCES:
        raise ValueError("VM55B-U rejects HDMI-PC source codes")
    allowed = {item.value for item in InputSource}
    if source not in allowed:
        raise ValueError("input source is not one of DVI, HDMI1, HDMI2, or DisplayPort")
    return source


def wall_div(rows: int, cols: int) -> int:
    if not 1 <= rows <= 15 or not 1 <= cols <= 15:
        raise ValueError("wall rows and columns must be 1–15")
    return (rows << 4) | cols
