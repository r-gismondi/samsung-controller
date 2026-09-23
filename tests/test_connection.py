import unittest

from samsung_controller.protocol import PanelOffline
from samsung_controller.session import open_connection


class OpenConnectionTests(unittest.TestCase):
    def test_connection_failures_stop_after_the_requested_attempts(self) -> None:
        attempts: list[int] = []

        def fail(address, timeout=None, source_address=None):
            attempts.append(address[1])
            raise OSError("refused")

        original = __import__("socket").create_connection
        try:
            __import__("socket").create_connection = fail
            with self.assertRaises(PanelOffline):
                open_connection("192.0.2.2", 1515, 0.1, attempts=2)
        finally:
            __import__("socket").create_connection = original
        self.assertEqual(attempts, [1515, 1515])


if __name__ == "__main__":
    unittest.main()
