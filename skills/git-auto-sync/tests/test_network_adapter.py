import unittest
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(SKILL_DIR / "scripts"))
import network_adapter


class DecideNetworkActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def base_env(self, **overrides):
        env = {
            "GIT_SYNC_TEST_DIRECT": "success",
            "GIT_SYNC_STATE_HOME": self.temp.name,
        }
        env.update(overrides)
        return env

    def test_direct_success(self):
        result = network_adapter.decide_network_action(self.base_env())
        self.assertEqual(result["outcome"], "direct")

    def test_three_failures_without_proxy_needs_choice(self):
        env = self.base_env(GIT_SYNC_TEST_DIRECT="fail")
        result = network_adapter.decide_network_action(env)
        self.assertEqual(result["outcome"], "need_choice")
        self.assertIn("diagnostics", result)

    def test_saved_proxy_fallback_when_alive(self):
        env = self.base_env(
            GIT_SYNC_TEST_DIRECT="fail",
            GIT_SYNC_TEST_SAVED_PROXY="http://127.0.0.1:7894",
            GIT_SYNC_TEST_PROXY_ALIVE="1",
        )
        result = network_adapter.decide_network_action(env)
        self.assertEqual(result["outcome"], "use_saved_proxy")
        self.assertEqual(result["proxy_url"], "http://127.0.0.1:7894")

    def test_dead_saved_proxy_needs_choice(self):
        env = self.base_env(
            GIT_SYNC_TEST_DIRECT="fail",
            GIT_SYNC_TEST_SAVED_PROXY="http://127.0.0.1:7894",
            GIT_SYNC_TEST_PROXY_ALIVE="0",
        )
        result = network_adapter.decide_network_action(env)
        self.assertEqual(result["outcome"], "need_choice")
        self.assertIn("saved_proxy_unreachable", result["reasons"])

    def test_retry_direct_has_a_hard_stop(self):
        env = self.base_env(
            GIT_SYNC_TEST_DIRECT="fail",
            GIT_SYNC_RETRY_DIRECT="1",
        )
        result = network_adapter.decide_network_action(env)
        self.assertEqual(result["outcome"], "direct_unavailable")

    def test_provided_proxy_used_once_without_saving(self):
        env = self.base_env(
            GIT_SYNC_TEST_DIRECT="fail",
            GIT_SYNC_PROXY="http://127.0.0.1:20891",
        )
        result = network_adapter.decide_network_action(env)
        self.assertEqual(result["outcome"], "use_provided_proxy")
        self.assertFalse(result["should_save"])

    def test_remember_flag_marks_save(self):
        env = self.base_env(
            GIT_SYNC_TEST_DIRECT="fail",
            GIT_SYNC_PROXY="http://127.0.0.1:20891",
            GIT_SYNC_REMEMBER_PROXY="1",
        )
        result = network_adapter.decide_network_action(env)
        self.assertTrue(result["should_save"])

    def test_residual_system_proxy_reason(self):
        env = self.base_env(
            GIT_SYNC_TEST_DIRECT="fail",
            GIT_SYNC_TEST_SYSTEM_PROXY="residual",
        )
        result = network_adapter.decide_network_action(env)
        self.assertIn("system_proxy_residual", result["reasons"])

    def test_live_system_proxy_is_node_issue(self):
        env = self.base_env(
            GIT_SYNC_TEST_DIRECT="fail",
            GIT_SYNC_TEST_SYSTEM_PROXY="node",
        )
        result = network_adapter.decide_network_action(env)
        self.assertIn("system_proxy_node_issue", result["reasons"])


if __name__ == "__main__":
    unittest.main()
