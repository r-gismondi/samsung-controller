"""The 18-panel room.

Two walls are 2×4. Screen index restarts at 1 on each wall, left to right and
top to bottom. Panels 17 and 18 are addressed and have no wall cell. Hosts come
from local configuration: panel N is ``{prefix}.{N + offset}``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from samsung_controller.protocol import DEFAULT_POWER_STAGGER_SECONDS, MdcError, wall_div

PANEL_COUNT = 18
MDC_PORT = 1515
WALL_ROWS = 2
WALL_COLS = 4
WALL_DIV = wall_div(WALL_ROWS, WALL_COLS)

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True)
class Wall:
    name: str
    rows: int
    cols: int
    panel_numbers: tuple[int, ...]


@dataclass(frozen=True)
class Cell:
    wall: str
    index: int
    row: int
    col: int


@dataclass(frozen=True)
class RoomConfig:
    network_prefix: str
    host_offset: int
    port: int
    panel_count: int

    def host_for(self, panel_number: int) -> str:
        if not 1 <= panel_number <= self.panel_count:
            raise ValueError(f"panel {panel_number} is outside 1–{self.panel_count}")
        last = panel_number + self.host_offset
        if not 1 <= last <= 254:
            raise ValueError(f"panel {panel_number} maps outside a usable last octet")
        return f"{self.network_prefix}.{last}"


@dataclass(frozen=True)
class CallResult:
    item: object
    value: object | None = None
    error: MdcError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


ROOM_WALLS = (
    Wall("wall-1", WALL_ROWS, WALL_COLS, tuple(range(1, 9))),
    Wall("wall-2", WALL_ROWS, WALL_COLS, tuple(range(9, 17))),
)
UNASSIGNED_PANELS = (17, 18)


def cell_for_panel(panel_number: int) -> Cell | None:
    if not 1 <= panel_number <= PANEL_COUNT:
        raise ValueError(f"panel {panel_number} is outside 1–{PANEL_COUNT}")
    for wall in ROOM_WALLS:
        if panel_number not in wall.panel_numbers:
            continue
        offset = panel_number - wall.panel_numbers[0]
        row, col = divmod(offset, wall.cols)
        return Cell(wall.name, offset + 1, row, col)
    return None


def stagger_times(
    count: int,
    gap: float = DEFAULT_POWER_STAGGER_SECONDS,
    start: float = 0.0,
) -> list[float]:
    if count < 0:
        raise ValueError("count must be zero or more")
    if gap < 0:
        raise ValueError("gap must be zero or more")
    return [start + index * gap for index in range(count)]


def run_each(items: Iterable[T], fn: Callable[[T], R]) -> list[CallResult]:
    """Run fn for every item. An MdcError on one item does not stop the rest."""
    results: list[CallResult] = []
    for item in items:
        try:
            results.append(CallResult(item, fn(item)))
        except MdcError as exc:
            results.append(CallResult(item, error=exc))
    return results


def load_config(path: str | Path) -> RoomConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("panel config must be a JSON object")
    prefix = _prefix(raw.get("network_prefix"))
    offset = _int_field(raw, "host_offset", 1)
    port = _int_field(raw, "port", MDC_PORT)
    count = _int_field(raw, "panel_count", PANEL_COUNT)
    if count != PANEL_COUNT:
        raise ValueError(f"panel_count must be {PANEL_COUNT}")
    if not 1 <= port <= 65535:
        raise ValueError("port must be 1–65535")
    config = RoomConfig(prefix, offset, port, count)
    for panel_number in range(1, count + 1):
        config.host_for(panel_number)
    return config


def hosts(config: RoomConfig) -> list[tuple[int, str]]:
    return [(number, config.host_for(number)) for number in range(1, config.panel_count + 1)]


def _prefix(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("network_prefix must be the first three dotted octets")
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError("network_prefix must be three decimal octets")
    numbers = [int(part) for part in parts]
    if any(number > 255 for number in numbers):
        raise ValueError("network_prefix octets must be 0–255")
    return ".".join(str(number) for number in numbers)


def _int_field(raw: dict[str, object], name: str, default: int) -> int:
    value = raw.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value
