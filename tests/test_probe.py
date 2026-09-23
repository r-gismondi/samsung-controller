import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from samsung_controller.fleet import RoomConfig
from samsung_controller.probe import PanelProbe, format_report, main, probe_room
from samsung_controller.protocol import CommandRejected, DeviceIdNotFound, PanelOffline, PanelStatus


class FakeSession:
    def __init__(self, script: dict[str, object]):
        self.script = script
        self.closed = False

    def probe(self) -> int:
        self._raise("probe")
        return int(self.script["device_id"])  # type: ignore[arg-type]

    def get_model_name(self) -> str:
        self._raise("model")
        return str(self.script["model"])

    def get_status(self) -> PanelStatus:
        self._raise("status")
        return self.script["status"]  # type: ignore[return-value]

    def get_backlight(self) -> int:
        self._raise("backlight")
        return int(self.script["backlight"])  # type: ignore[arg-type]

    def get_panel_power(self) -> int:
        self._raise("panel_power")
        return int(self.script["panel_power"])  # type: ignore[arg-type]

    def close(self) -> None:
        self.closed = True

    def _raise(self, key: str) -> None:
        error = self.script.get(f"fail_{key}")
        if error is not None:
            raise error  # type: ignore[misc]


class ProbeTests(unittest.TestCase):
    def test_one_offline_panel_does_not_stop_the_sweep(self) -> None:
        sessions: list[FakeSession] = []

        def connect(host: str, port: int, timeout: float) -> str:
            if host.endswith(".2"):
                raise PanelOffline("timed out")
            return host

        def factory(transport: object) -> FakeSession:
            session = FakeSession(
                {
                    "device_id": 4,
                    "model": "VM55B-U",
                    "status": PanelStatus(1, 10, 0, 0x21, 1),
                    "backlight": 80,
                    "panel_power": 1,
                }
            )
            sessions.append(session)
            return session

        config = RoomConfig("192.0.2", 1, 1515, 18)
        results = probe_room(config, panels=(1, 2), timeout=0.2, connect=connect, session_factory=factory)
        self.assertFalse(results[0].tcp_open)
        self.assertTrue(results[0].error.startswith("offline:"))
        self.assertEqual(results[1].device_id, 4)
        self.assertEqual(results[1].model, "VM55B-U")
        self.assertEqual((results[1].power, results[1].source, results[1].backlight), (1, 0x21, 80))
        self.assertTrue(sessions[0].closed)

    def test_open_socket_without_an_ack_is_recorded(self) -> None:
        def connect(host: str, port: int, timeout: float) -> str:
            return host

        def factory(transport: object) -> FakeSession:
            return FakeSession({"fail_probe": DeviceIdNotFound("none")})

        config = RoomConfig("192.0.2", 1, 1515, 18)
        result = probe_room(config, panels=(9,), connect=connect, session_factory=factory)[0]
        self.assertTrue(result.tcp_open)
        self.assertIsNone(result.device_id)
        self.assertEqual(result.error, "none")

    def test_report_and_cli_write_json_without_sending(self) -> None:
        report = format_report(
            [PanelProbe(1, "192.0.2.2", True, 0, "VM55B-U", 1, 10, 0, 0x21, 1, 40, 1)]
        )
        self.assertIn("VM55B-U", report)
        self.assertIn("panel", report)


    def test_a_nak_on_backlight_keeps_the_identity(self) -> None:
        def connect(host: str, port: int, timeout: float) -> str:
            return host

        def factory(transport: object) -> FakeSession:
            return FakeSession(
                {
                    "device_id": 1,
                    "model": "VM55B-U",
                    "status": PanelStatus(1, 0, 0, 0x21, 0),
                    "fail_backlight": CommandRejected(0x58, 0x01),
                    "panel_power": 1,
                }
            )

        config = RoomConfig("192.0.2", 1, 1515, 18)
        result = probe_room(config, panels=(1,), connect=connect, session_factory=factory)[0]
        self.assertEqual(result.device_id, 1)
        self.assertEqual(result.model, "VM55B-U")
        self.assertIsNone(result.backlight)
        self.assertEqual(result.panel_power, 1)
        self.assertIn("backlight:", result.error or "")


class CliTests(unittest.TestCase):
    def test_missing_config_fails_before_any_network_call(self) -> None:
        with self.assertRaises(FileNotFoundError):
            main(["--config", "config/does-not-exist.json", "--panels", "1"])

    def test_output_file_contains_the_panel_record(self) -> None:
        record = PanelProbe(1, "192.0.2.2", True, 0, "VM55B-U", 1, 10, 0, 0x21, 1, 40, 1)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "probe.json"
            with (
                patch("samsung_controller.probe.load_config", return_value=RoomConfig("192.0.2", 1, 1515, 18)),
                patch("samsung_controller.probe.probe_room", return_value=[record]) as probed,
                redirect_stdout(io.StringIO()),
            ):
                code = main(["--config", "unused.json", "--panels", "1", "--output", str(destination)])
            self.assertEqual(code, 0)
            probed.assert_called_once()
            saved = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["panel"], 1)
        self.assertEqual(saved[0]["model"], "VM55B-U")


if __name__ == "__main__":
    unittest.main()
