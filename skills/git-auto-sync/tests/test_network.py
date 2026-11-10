import unittest
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import network


class ProbeTests(unittest.TestCase):
    def test_tcp_probe_success_uses_timeout(self):
        calls = []

        def fake_probe(host, port, timeout):
            calls.append((host, port, timeout))
            return True

        self.assertTrue(network.tcp_reachable("github.com", 443, timeout=6, probe=fake_probe))
        self.assertEqual(calls, [("github.com", 443, 6)])

    def test_tcp_probe_failure_returns_false(self):
        def fake_probe(host, port, timeout):
            return False

        self.assertFalse(network.tcp_reachable("github.com", 443, probe=fake_probe))

    def test_default_probe_catches_socket_error(self):
        def fake_socket(*args, **kwargs):
            raise OSError("boom")

        self.assertFalse(network.tcp_reachable("127.0.0.1", 1, socket_factory=fake_socket))

    def test_github_direct_checks_443_and_22(self):
        seen = []

        def fake_probe(host, port, timeout):
            seen.append(port)
            return port == 443

        result = network.check_github_direct(probe=fake_probe)
        self.assertTrue(result.port_443)
        self.assertFalse(result.port_22)
        self.assertEqual(seen, [443, 22])


class DirectRetryTests(unittest.TestCase):
    def test_success_on_first_attempt_stops_retrying(self):
        attempts = []

        def fake_probe(host, port, timeout):
            attempts.append(port)
            return True

        result = network.wait_for_direct(
            attempts=3, timeout=6,
            probe=fake_probe, sleep=lambda _: None,
        )
        self.assertTrue(result)
        self.assertEqual(attempts, [443])

    def test_three_failures_return_false_and_measure_delays(self):
        delays = []

        def fake_probe(host, port, timeout):
            return False

        result = network.wait_for_direct(
            attempts=3, timeout=6,
            probe=fake_probe, sleep=delays.append,
        )
        self.assertFalse(result)
        self.assertEqual(len(delays), 2)
        self.assertTrue(all(1 <= delay <= 2 for delay in delays))

    def test_success_on_third_attempt(self):
        state = {"count": 0}

        def fake_probe(host, port, timeout):
            state["count"] += 1
            return state["count"] == 3

        result = network.wait_for_direct(
            attempts=3, timeout=6,
            probe=fake_probe, sleep=lambda _: None,
        )
        self.assertTrue(result)
        self.assertEqual(state["count"], 3)


class SystemProxyTests(unittest.TestCase):
    @staticmethod
    def registry(enable, server):
        def fake_read():
            return {"ProxyEnable": enable, "ProxyServer": server}
        return fake_read

    def test_disabled_switch_returns_none(self):
        status = network.detect_system_proxy(
            registry_reader=self.registry(0, "127.0.0.1:7890"),
            port_probe=lambda port: True,
        )
        self.assertIsNone(status)

    def test_enabled_with_dead_port_is_residual(self):
        status = network.detect_system_proxy(
            registry_reader=self.registry(1, "127.0.0.1:7890"),
            port_probe=lambda port: False,
        )
        self.assertEqual(status.host, "127.0.0.1")
        self.assertEqual(status.port, 7890)
        self.assertFalse(status.port_listening)
        self.assertTrue(status.residual)

    def test_enabled_with_live_port_is_node_issue_not_residual(self):
        status = network.detect_system_proxy(
            registry_reader=self.registry(1, "127.0.0.1:7890"),
            port_probe=lambda port: True,
        )
        self.assertTrue(status.port_listening)
        self.assertFalse(status.residual)

    def test_proxy_server_with_scheme_and_extras(self):
        status = network.detect_system_proxy(
            registry_reader=self.registry(1, "http=127.0.0.1:7890;https=127.0.0.1:7891"),
            port_probe=lambda port: False,
        )
        self.assertEqual(status.port, 7890)
        self.assertTrue(status.residual)

    def test_unsupported_platform_returns_none(self):
        def no_registry():
            raise network.RegistryUnavailable("非 Windows 平台")

        status = network.detect_system_proxy(
            registry_reader=no_registry,
            port_probe=lambda port: True,
        )
        self.assertIsNone(status)

    def test_malformed_server_returns_none(self):
        status = network.detect_system_proxy(
            registry_reader=self.registry(1, "没有端口的坏值"),
            port_probe=lambda port: True,
        )
        self.assertIsNone(status)


if __name__ == "__main__":
    unittest.main()
