import json
import unittest
from pathlib import Path

from samsung_controller.fleet import (
    PANEL_COUNT,
    UNASSIGNED_PANELS,
    WALL_DIV,
    CallResult,
    RoomConfig,
    cell_for_panel,
    hosts,
    load_config,
    run_each,
    stagger_times,
)
from samsung_controller.protocol import PanelOffline


class LayoutTests(unittest.TestCase):
    def test_each_wall_is_2_by_4_and_restarts_its_index(self) -> None:
        self.assertEqual(WALL_DIV, 0x24)
        first = cell_for_panel(1)
        last_on_first = cell_for_panel(8)
        second = cell_for_panel(9)
        last_on_second = cell_for_panel(16)
        assert first is not None and last_on_first is not None
        assert second is not None and last_on_second is not None
        self.assertEqual((first.wall, first.index, first.row, first.col), ("wall-1", 1, 0, 0))
        self.assertEqual((last_on_first.index, last_on_first.row, last_on_first.col), (8, 1, 3))
        self.assertEqual((second.wall, second.index), ("wall-2", 1))
        self.assertEqual(last_on_second.index, 8)
        self.assertEqual(UNASSIGNED_PANELS, (17, 18))
        self.assertIsNone(cell_for_panel(17))
        self.assertIsNone(cell_for_panel(18))

    def test_panel_four_is_the_end_of_the_first_row(self) -> None:
        cell = cell_for_panel(4)
        assert cell is not None
        self.assertEqual((cell.index, cell.row, cell.col), (4, 0, 3))


class ConfigTests(unittest.TestCase):
    def test_example_config_uses_the_documentation_prefix(self) -> None:
        config = load_config(Path("config/panels.example.json"))
        self.assertEqual(config.network_prefix, "192.0.2")
        self.assertEqual(hosts(config)[0], (1, "192.0.2.2"))
        self.assertEqual(hosts(config)[-1], (18, "192.0.2.19"))
        self.assertEqual(len(hosts(config)), PANEL_COUNT)
        for _, host in hosts(config):
            self.assertFalse(host.startswith("192.168.0."))

    def test_offset_is_configurable(self) -> None:
        config = RoomConfig("10.0.0", 10, 1515, 18)
        self.assertEqual(config.host_for(1), "10.0.0.11")

    def test_loader_rejects_a_different_room_size(self) -> None:
        path = Path("config/panels.example.json")
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["panel_count"] = 10
        rejected = path.with_name("panels.rejected.json")
        rejected.write_text(json.dumps(raw), encoding="utf-8")
        self.addCleanup(rejected.unlink)
        with self.assertRaises(ValueError):
            load_config(rejected)


class RunEachTests(unittest.TestCase):
    def test_one_offline_panel_does_not_stop_the_others(self) -> None:
        def send(panel: int) -> str:
            if panel == 2:
                raise PanelOffline("down")
            return f"ok-{panel}"

        results = run_each([1, 2, 3], send)
        self.assertTrue(results[0].ok)
        self.assertIsInstance(results[1].error, PanelOffline)
        self.assertEqual(results[2].value, "ok-3")
        self.assertTrue(all(isinstance(item, CallResult) for item in results))

    def test_power_stagger_spreads_the_sets(self) -> None:
        self.assertEqual(stagger_times(3, gap=5, start=10), [10, 15, 20])


if __name__ == "__main__":
    unittest.main()
