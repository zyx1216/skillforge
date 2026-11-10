import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "sync.py"


def git(repo, *args):
    env = os.environ.copy()
    env["LC_ALL"] = "C.UTF-8"
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True,
        encoding="utf-8", capture_output=True, env=env,
    ).stdout.strip()


class SyncNetworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.state_home = base / "state"
        self.remote = base / "remote.git"
        self.repo = base / "repo"
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True, capture_output=True)
        subprocess.run(["git", "init", "-b", "main", str(self.repo)], check=True, capture_output=True)
        git(self.repo, "config", "user.name", "测试用户")
        git(self.repo, "config", "user.email", "test@example.com")
        (self.repo / "README.md").write_text("初始\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-m", "chore: 初始化")
        git(self.repo, "remote", "add", "origin", str(self.remote))

    def tearDown(self):
        self.temp.cleanup()

    def sync(self, *args, extra_env=None):
        env = os.environ.copy()
        env["LC_ALL"] = "C.UTF-8"
        env["PYTHONUTF8"] = "1"
        env["GIT_SYNC_STATE_HOME"] = str(self.state_home)
        env["GIT_SYNC_TEST_DIRECT"] = "success"
        if extra_env:
            env.update(extra_env)
        command = [sys.executable, str(SCRIPT), "--allow-dirty", *args]
        return subprocess.run(
            command, cwd=self.repo, text=True,
            encoding="utf-8", capture_output=True, env=env,
        )

    def change_readme(self, text="网络状态机改动\n"):
        (self.repo / "README.md").write_text(text, encoding="utf-8")

    def test_three_direct_failures_before_commit_asks_and_keeps_changes(self):
        self.change_readme()
        head_before = git(self.repo, "rev-parse", "HEAD")
        result = self.sync(
            "--message", "docs: 三败询问", "--", "README.md",
            extra_env={"GIT_SYNC_TEST_DIRECT": "fail"},
        )
        self.assertEqual(result.returncode, 7)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "network_choice_required")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head_before)

    def test_direct_success_pushes_normally(self):
        self.change_readme()
        result = self.sync(
            "--message", "docs: 直连成功", "--", "README.md",
            extra_env={"GIT_SYNC_TEST_DIRECT": "success"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "pushed")

    def test_retry_direct_stops_after_second_round(self):
        self.change_readme()
        head_before = git(self.repo, "rev-parse", "HEAD")
        result = self.sync(
            "--message", "docs: 继续直连止境", "--", "README.md",
            extra_env={"GIT_SYNC_TEST_DIRECT": "fail", "GIT_SYNC_RETRY_DIRECT": "1"},
        )
        self.assertEqual(result.returncode, 7)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "direct_unavailable")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head_before)

    def test_provided_proxy_pushes_without_saving(self):
        self.change_readme()
        result = self.sync(
            "--message", "docs: 一次性代理", "--", "README.md",
            extra_env={
                "GIT_SYNC_TEST_DIRECT": "fail",
                "GIT_SYNC_PROXY": "http://127.0.0.1:20891",
                "GIT_SYNC_TEST_PROXY_ALIVE": "1",
                "GIT_SYNC_TEST_TUNNEL": "1",
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "pushed")
        self.assertFalse(self.state_home.exists())


if __name__ == "__main__":
    unittest.main()

