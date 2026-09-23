import unittest

from samsung_controller.protocol import (
    CMD_MANUAL_LAMP,
    CMD_POWER,
    CMD_VOLUME,
    POWER_SETTLE_SECONDS,
    BadFrame,
    CommandRejected,
    ConnectionClosed,
    DeviceIdNotFound,
    InputSource,
    PanelOffline,
    PanelSettling,
    ResponseTimeout,
    checksum,
    encode,
)
from samsung_controller.session import Session


def ack(device_id: int, command: int, data: bytes = b"") -> bytes:
    tail = bytes((ord("A"), command)) + data
    body = bytes((0xFF, device_id, len(tail))) + tail
    return bytes((0xAA,)) + body + bytes((checksum(body),))


def nak(device_id: int, error: int) -> bytes:
    body = bytes((0xFF, device_id, 2, ord("N"), error))
    return bytes((0xAA,)) + body + bytes((checksum(body),))


class QueueTransport:
    def __init__(self, events: list[object]):
        self.events = list(events)
        self.sent: list[bytes] = []
        self.buffer = bytearray()
        self.closed = False

    def sendall(self, data: bytes) -> None:
        self.sent.append(bytes(data))

    def recv_exact(self, size: int) -> bytes:
        while len(self.buffer) < size:
            if not self.events:
                raise ConnectionClosed("no more data")
            event = self.events.pop(0)
            if isinstance(event, BaseException):
                raise event
            if not isinstance(event, bytes):
                raise AssertionError("scripted event must be bytes or an exception")
            self.buffer += event
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def close(self) -> None:
        self.closed = True


class ProbeTests(unittest.TestCase):
    def test_probe_keeps_the_first_id_that_acks(self) -> None:
        transport = QueueTransport(
            [
                ResponseTimeout("id 0"),
                nak(1, 0x01),
                ack(2, CMD_POWER, bytes((1,))),
                ack(3, CMD_POWER, bytes((1,))),
            ]
        )
        session = Session(transport)
        self.assertEqual(session.probe(), 2)
        sent_ids = [frame[2] for frame in transport.sent]
        self.assertEqual(sent_ids, [0, 1, 2])
        self.assertNotIn(0xFE, sent_ids)
        self.assertEqual(transport.sent[0], encode(CMD_POWER, 0, b""))

    def test_closed_socket_stops_the_probe(self) -> None:
        transport = QueueTransport([ConnectionClosed("reset")])
        session = Session(transport)
        with self.assertRaises(PanelOffline):
            session.probe()
        self.assertEqual(len(transport.sent), 1)

    def test_no_ack_raises_without_using_the_broadcast_id(self) -> None:
        transport = QueueTransport([ResponseTimeout("silent")] * 11)
        session = Session(transport)
        with self.assertRaises(DeviceIdNotFound):
            session.probe()
        self.assertEqual([frame[2] for frame in transport.sent], list(range(11)))


class CommandTests(unittest.TestCase):
    def test_nak_is_not_retried(self) -> None:
        transport = QueueTransport([nak(4, 0x22)])
        session = Session(transport, device_id=4)
        with self.assertRaises(CommandRejected) as caught:
            session.set_volume(10)
        self.assertEqual(caught.exception.error_code, 0x22)
        self.assertEqual(len(transport.sent), 1)

    def test_timeout_after_the_id_is_known_is_offline(self) -> None:
        transport = QueueTransport([ResponseTimeout("late")])
        session = Session(transport, device_id=1)
        with self.assertRaises(PanelOffline):
            session.get_power()

    def test_bad_checksum_is_not_a_panel_fault(self) -> None:
        broken = bytearray(ack(1, CMD_POWER, bytes((1,))))
        broken[-1] ^= 0xFF
        transport = QueueTransport([bytes(broken)])
        session = Session(transport, device_id=1)
        with self.assertRaises(BadFrame):
            session.get_power()

    def test_power_set_blocks_the_next_command_until_settle(self) -> None:
        transport = QueueTransport(
            [
                ack(1, CMD_POWER, bytes((1,))),
                ack(1, CMD_MANUAL_LAMP, bytes((40,))),
            ]
        )
        moments = [100.0, 100.0 + POWER_SETTLE_SECONDS - 0.1, 100.0 + POWER_SETTLE_SECONDS]
        session = Session(
            transport,
            device_id=1,
            settle_seconds=POWER_SETTLE_SECONDS,
            clock=lambda: moments.pop(0),
        )
        session.set_power(True)
        with self.assertRaises(PanelSettling):
            session.set_backlight(40)
        self.assertEqual(len(transport.sent), 1)
        self.assertEqual(session.set_backlight(40), None)
        self.assertEqual(transport.sent[1], encode(CMD_MANUAL_LAMP, 1, bytes((40,))))

    def test_panel_blank_does_not_start_the_power_settle_gate(self) -> None:
        transport = QueueTransport(
            [
                ack(1, 0xF9, bytes((0,))),
                ack(1, CMD_VOLUME, bytes((3,))),
            ]
        )
        session = Session(transport, device_id=1, clock=lambda: 0.0)
        session.set_panel_power(False)
        self.assertEqual(session.set_volume(3), None)

    def test_rejected_inputs_are_not_sent(self) -> None:
        transport = QueueTransport([])
        session = Session(transport, device_id=1)
        with self.assertRaises(ValueError):
            session.set_input(0x22)
        with self.assertRaises(ValueError):
            session.set_backlight(101)
        self.assertEqual(transport.sent, [])
        self.assertEqual(InputSource.DISPLAY_PORT, 0x25)


if __name__ == "__main__":
    unittest.main()
