import unittest

from samsung_controller.protocol import (
    CMD_INPUT,
    CMD_MANUAL_LAMP,
    CMD_PANEL_ON_OFF,
    CMD_POWER,
    CMD_VIDEO_WALL_LAYOUT,
    HDMI_PC_SOURCES,
    VIDEO_WALL_MODE_FULL,
    VIDEO_WALL_MODE_NATURAL,
    BadFrame,
    InputSource,
    checksum,
    encode,
    parse,
    parse_model_name,
    parse_status,
    require_input,
    wall_div,
)


def frame(*parts: int) -> bytes:
    body = bytes(parts)
    return bytes((0xAA,)) + body + bytes((checksum(body),))


class EncodeTests(unittest.TestCase):
    def test_power_and_input_vectors(self) -> None:
        self.assertEqual(encode(CMD_POWER, 0, bytes((0,))), bytes.fromhex("aa1100010012"))
        self.assertEqual(encode(CMD_POWER, 0, bytes((1,))), bytes.fromhex("aa1100010113"))
        self.assertEqual(encode(CMD_INPUT, 0, bytes((0x21,))), bytes.fromhex("aa1400012136"))
        self.assertEqual(encode(CMD_PANEL_ON_OFF, 0, bytes((0,))), bytes.fromhex("aaf9000100fa"))

    def test_backlight_and_wall_layout_include_the_device_id(self) -> None:
        self.assertEqual(encode(CMD_MANUAL_LAMP, 3, bytes((100,))), bytes.fromhex("aa58030164c0"))
        self.assertEqual(
            encode(CMD_VIDEO_WALL_LAYOUT, 0, bytes((0x24, 1))),
            bytes.fromhex("aa8900022401b0"),
        )

    def test_broadcast_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            encode(CMD_POWER, 0xFE, b"")

    def test_wall_div_for_the_drawn_grids_is_2_by_4(self) -> None:
        self.assertEqual(wall_div(2, 4), 0x24)

    def test_video_wall_mode_values_stay_on_the_general_spec(self) -> None:
        self.assertEqual((VIDEO_WALL_MODE_NATURAL, VIDEO_WALL_MODE_FULL), (0x00, 0x01))


class ParseTests(unittest.TestCase):
    def test_ack_power_on(self) -> None:
        response = parse(frame(0xFF, 0x00, 0x03, ord("A"), CMD_POWER, 0x01))
        self.assertTrue(response.ack)
        self.assertEqual(response.command, CMD_POWER)
        self.assertEqual(response.data, bytes((0x01,)))

    def test_nak_with_only_an_error_byte(self) -> None:
        response = parse(frame(0xFF, 0x04, 0x02, ord("N"), 0x0A))
        self.assertFalse(response.ack)
        self.assertIsNone(response.command)
        self.assertEqual(response.error_code, 0x0A)

    def test_nak_with_command_then_error(self) -> None:
        response = parse(frame(0xFF, 0x04, 0x03, ord("N"), CMD_POWER, 0x0B))
        self.assertEqual(response.command, CMD_POWER)
        self.assertEqual(response.error_code, 0x0B)

    def test_bad_checksum_is_a_bad_frame(self) -> None:
        broken = bytearray(frame(0xFF, 0x00, 0x03, ord("A"), CMD_POWER, 0x01))
        broken[-1] ^= 0xFF
        with self.assertRaises(BadFrame):
            parse(bytes(broken))

    def test_status_and_model_name(self) -> None:
        status = parse_status(bytes((1, 20, 0, 0x21, 0x01, 0x00, 0x00)))
        self.assertEqual((status.power, status.volume, status.source), (1, 20, 0x21))
        self.assertEqual(parse_model_name(b"VM55B-U\x00extra"), "VM55B-U")

    def test_short_status_is_rejected(self) -> None:
        with self.assertRaises(BadFrame):
            parse_status(bytes((1, 2, 3)))

    def test_hdmi_pc_sources_cannot_be_set(self) -> None:
        for source in HDMI_PC_SOURCES:
            with self.assertRaises(ValueError):
                require_input(source)
        self.assertEqual(require_input(InputSource.HDMI1), 0x21)


if __name__ == "__main__":
    unittest.main()
