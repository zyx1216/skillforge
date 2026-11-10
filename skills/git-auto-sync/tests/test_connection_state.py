import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(SKILL_DIR / "scripts"))
import connection


class StateMachineTests(unittest.TestCase):
    def make_policy(
        self, direct_results=None, proxy_port_probe=None,
        saved_proxy=None, system_proxy=None, remember=False,
        retry_direct=False, provided_proxy=None,
        git_proxy=None, env_proxy=None,
        direct_checks=None,
        proxy_tunnel_probe=None,
    ):
        if direct_checks is not None:
            checks = list(direct_checks)
            direct_probe = lambda: checks.pop(0)
        else:
            direct = list(direct_results or [])
            direct_probe = lambda: direct.pop(0) if direct else False

        return connection.ConnectionPolicy(
            direct_probe=direct_probe,
            proxy_port_probe=proxy_port_probe or (lambda url: True),
            saved_proxy=saved_proxy,
            system_proxy=system_proxy,
            remember=remember,
            provided_proxy=provided_proxy,
            retry_direct=retry_direct,
            sleep=lambda _: None,
            git_proxy=git_proxy,
            env_proxy=env_proxy,
            proxy_tunnel_probe=proxy_tunnel_probe,
        )

    def test_direct_success_returns_direct_without_diagnostics(self):
        policy = self.make_policy(direct_results=[True])
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.DIRECT)

    def test_three_direct_failures_asks_user_when_no_saved_proxy(self):
        policy = self.make_policy(direct_results=[False, False, False])
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.NEED_CHOICE)
        self.assertTrue(decision.diagnostics)

    def test_diagnostics_include_git_and_env_proxy(self):
        policy = self.make_policy(
            direct_results=[False, False, False],
            git_proxy={"http_proxy": "http://127.0.0.1:20890", "https_proxy": "http://127.0.0.1:20890"},
            env_proxy={"http_proxy": None, "https_proxy": "socks5h://127.0.0.1:7894", "all_proxy": None},
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(
            decision.diagnostics["git_proxy"],
            {"http_proxy": "http://127.0.0.1:20890", "https_proxy": "http://127.0.0.1:20890"},
        )
        self.assertEqual(
            decision.diagnostics["env_proxy"]["https_proxy"],
            "socks5h://127.0.0.1:7894",
        )

    def test_direct_probe_reports_both_ports_in_diagnostics(self):
        policy = self.make_policy(
            direct_results=[False, False, False],
            direct_checks=[
                connection.DirectPorts(False, True),
                connection.DirectPorts(False, True),
                connection.DirectPorts(False, True),
            ],
        )
        decision = connection.plan_connection(policy)
        self.assertFalse(decision.diagnostics["direct_ports"]["port_443"])
        self.assertTrue(decision.diagnostics["direct_ports"]["port_22"])
        self.assertIn("ssh_available", decision.reasons)

    def test_three_failures_auto_falls_back_to_saved_proxy(self):
        policy = self.make_policy(
            direct_results=[False, False, False],
            saved_proxy="http://127.0.0.1:7894",
            proxy_tunnel_probe=lambda url: True,
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.USE_SAVED_PROXY)
        self.assertEqual(decision.proxy_url, "http://127.0.0.1:7894")

    def test_dead_saved_proxy_asks_again_instead_of_looping(self):
        policy = self.make_policy(
            direct_results=[False, False, False],
            saved_proxy="http://127.0.0.1:7894",
            proxy_port_probe=lambda url: False,
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.NEED_CHOICE)
        self.assertIn("saved_proxy_unreachable", decision.reasons)

    def test_saved_http_proxy_with_broken_tunnel_asks_again(self):
        policy = self.make_policy(
            direct_results=[False, False, False],
            saved_proxy="http://127.0.0.1:7894",
            proxy_port_probe=lambda url: True,
            proxy_tunnel_probe=lambda url: False,
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.NEED_CHOICE)
        self.assertIn("proxy_node_failed", decision.reasons)

    def test_provided_http_proxy_with_broken_tunnel_asks_again(self):
        policy = self.make_policy(
            direct_results=[False, False, False],
            provided_proxy="http://127.0.0.1:20891",
            proxy_port_probe=lambda url: True,
            proxy_tunnel_probe=lambda url: False,
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.NEED_CHOICE)
        self.assertIn("proxy_node_failed", decision.reasons)

    def test_socks_proxy_skips_tunnel_and_uses_port_check(self):
        policy = self.make_policy(
            direct_results=[False, False, False],
            saved_proxy="socks5h://127.0.0.1:7894",
            proxy_port_probe=lambda url: True,
            proxy_tunnel_probe=lambda url: False,
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.USE_SAVED_PROXY)

    def test_retry_direct_runs_another_round_then_stops(self):
        policy = self.make_policy(
            direct_results=[False, False, False, False, False, False],
            retry_direct=True,
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.DIRECT_UNAVAILABLE)
        self.assertEqual(policy.direct_attempts, 6)

    def test_retry_direct_succeeds_in_second_round(self):
        policy = self.make_policy(
            direct_results=[False, False, False, True],
            retry_direct=True,
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.DIRECT)

    def test_user_provided_proxy_is_used_once_when_not_remembered(self):
        policy = self.make_policy(
            direct_results=[False, False, False],
            provided_proxy="socks5h://127.0.0.1:7894",
            remember=False,
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.USE_PROVIDED_PROXY)
        self.assertEqual(decision.proxy_url, "socks5h://127.0.0.1:7894")
        self.assertFalse(decision.should_save)

    def test_remembered_proxy_is_marked_to_save(self):
        policy = self.make_policy(
            direct_results=[False, False, False],
            provided_proxy="http://127.0.0.1:20891",
            remember=True,
            proxy_tunnel_probe=lambda url: True,
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.USE_PROVIDED_PROXY)
        self.assertTrue(decision.should_save)

    def test_residual_system_proxy_is_reported(self):
        status = connection.SystemProxyInfo(
            host="127.0.0.1", port=7890, listening=False, residual=True,
        )
        policy = self.make_policy(
            direct_results=[False, False, False], system_proxy=status,
        )
        decision = connection.plan_connection(policy)
        self.assertEqual(decision.outcome, connection.NEED_CHOICE)
        self.assertIn("system_proxy_residual", decision.reasons)

    def test_live_system_proxy_is_node_issue_not_residual(self):
        status = connection.SystemProxyInfo(
            host="127.0.0.1", port=7890, listening=True, residual=False,
        )
        policy = self.make_policy(
            direct_results=[False, False, False], system_proxy=status,
        )
        decision = connection.plan_connection(policy)
        self.assertIn("system_proxy_node_issue", decision.reasons)
        self.assertNotIn("system_proxy_residual", decision.reasons)


if __name__ == "__main__":
    unittest.main()
