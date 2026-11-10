import json
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(SKILL_DIR / "scripts"))
import proxy_pref


class ProxyPreferenceTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_save_and_load_loopback_proxy(self):
        proxy_pref.save_preference("http://127.0.0.1:7894", home=self.home)
        loaded = proxy_pref.load_preference(home=self.home)
        self.assertEqual(loaded.proxy_url, "http://127.0.0.1:7894")
        self.assertFalse(loaded.remote_risk)

    def test_missing_file_returns_none(self):
        self.assertIsNone(proxy_pref.load_preference(home=self.home))

    def test_clear_removes_file(self):
        proxy_pref.save_preference("http://127.0.0.1:7894", home=self.home)
        proxy_pref.clear_preference(home=self.home)
        self.assertIsNone(proxy_pref.load_preference(home=self.home))

    def test_remote_proxy_is_flagged_as_risk(self):
        preference = proxy_pref.save_preference("http://10.20.30.40:8080", home=self.home)
        self.assertTrue(preference.remote_risk)
        self.assertTrue(proxy_pref.load_preference(home=self.home).remote_risk)

    def test_socks5h_loopback_is_safe(self):
        preference = proxy_pref.save_preference("socks5h://127.0.0.1:7894", home=self.home)
        self.assertFalse(preference.remote_risk)

    def test_corrupt_file_returns_none_and_does_not_raise(self):
        path = self.home / ".git-auto-sync" / "proxy.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{坏 json", encoding="utf-8")
        self.assertIsNone(proxy_pref.load_preference(home=self.home))

    def test_state_file_is_hidden_dot_dir_not_repo(self):
        proxy_pref.save_preference("http://127.0.0.1:7894", home=self.home)
        path = self.home / ".git-auto-sync" / "proxy.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["proxy_url"], "http://127.0.0.1:7894")
        self.assertIn("saved_at", data)


if __name__ == "__main__":
    unittest.main()
