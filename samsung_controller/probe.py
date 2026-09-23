"""Read-only probe of the VM55B-U room.

Each panel gets its own socket. The only MDC traffic is a power query for
device ids 0–10, then get-commands for model, status, backlight, and panel
power. Nothing here changes power, backlight, input, or wall layout.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from samsung_controller.fleet import RoomConfig, load_config
from samsung_controller.protocol import (
    DeviceIdNotFound,
    MdcError,
    PanelOffline,
    PanelStatus,
)
from samsung_controller.session import Session, SocketTransport, open_connection

Connect = Callable[[str, int, float], object]
SessionFactory = Callable[[object], Session]


@dataclass
class PanelProbe:
    panel: int
    host: str
    tcp_open: bool
    device_id: int | None = None
    model: str | None = None
    power: int | None = None
    volume: int | None = None
    mute: int | None = None
    source: int | None = None
    aspect: int | None = None
    backlight: int | None = None
    panel_power: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def probe_room(
    config: RoomConfig,
    panels: Sequence[int] | None = None,
    timeout: float = 5.0,
    connect: Connect | None = None,
    session_factory: SessionFactory | None = None,
) -> list[PanelProbe]:
    selected = tuple(range(1, config.panel_count + 1) if panels is None else panels)
    for panel in selected:
        config.host_for(panel)
    opener = connect or _connect
    factory = session_factory or _session
    return [
        _probe_one(panel, config.host_for(panel), config.port, timeout, opener, factory)
        for panel in selected
    ]


def format_report(results: Sequence[PanelProbe]) -> str:
    lines = ["panel  tcp  id  model      power  backlight  panel  error"]
    for item in results:
        lines.append(
            f"{item.panel:02d}     "
            f"{'yes' if item.tcp_open else 'no ':3}  "
            f"{_cell(item.device_id):2}  "
            f"{(item.model or '-'):10} "
            f"{_cell(item.power):5}  "
            f"{_cell(item.backlight):9}  "
            f"{_cell(item.panel_power):5}  "
            f"{item.error or ''}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read panel identity and status over MDC.")
    parser.add_argument("--config", default="config/panels.json", help="Local room config")
    parser.add_argument("--panels", help="Comma-separated panel numbers, default all")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output", help="Write the JSON results to this path")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    panels = _parse_panels(args.panels) if args.panels else None
    results = probe_room(config, panels, args.timeout)
    payload = [item.to_dict() for item in results]
    text = json.dumps(payload, indent=2)
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text + "\n", encoding="utf-8")
    print(format_report(results))
    if args.output:
        print(args.output)
    return 0 if all(item.tcp_open and item.device_id is not None and not item.error for item in results) else 1


def _probe_one(
    panel: int,
    host: str,
    port: int,
    timeout: float,
    connect: Connect,
    session_factory: SessionFactory,
) -> PanelProbe:
    record = PanelProbe(panel, host, False)
    try:
        transport = connect(host, port, timeout)
    except PanelOffline as exc:
        record.error = f"offline: {exc}"
        return record
    record.tcp_open = True
    session = session_factory(transport)
    try:
        try:
            record.device_id = session.probe()
        except DeviceIdNotFound as exc:
            record.error = str(exc)
            return record
        except MdcError as exc:
            record.error = f"probe: {exc}"
            return record
        record.model = _read(session.get_model_name, record, "model")
        status = _read(session.get_status, record, "status")
        if isinstance(status, PanelStatus):
            record.power = status.power
            record.volume = status.volume
            record.mute = status.mute
            record.source = status.source
            record.aspect = status.aspect
        record.backlight = _read(session.get_backlight, record, "backlight")
        record.panel_power = _read(session.get_panel_power, record, "panel-power")
    finally:
        session.close()
    return record


def _read(fn: Callable[[], object], record: PanelProbe, label: str) -> object | None:
    try:
        return fn()
    except MdcError as exc:
        note = f"{label}: {exc}"
        record.error = note if record.error is None else f"{record.error}; {note}"
        return None


def _connect(host: str, port: int, timeout: float) -> SocketTransport:
    return SocketTransport(open_connection(host, port, timeout, attempts=1))


def _session(transport: object) -> Session:
    return Session(transport)  # type: ignore[arg-type]


def _parse_panels(value: str) -> list[int]:
    panels = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        panels.append(int(part))
    if not panels:
        raise SystemExit("panel list is empty")
    return panels


def _cell(value: int | None) -> str:
    return "-" if value is None else str(value)


if __name__ == "__main__":
    sys.exit(main())
