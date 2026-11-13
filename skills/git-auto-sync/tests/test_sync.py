import json
import http.server
import os
import subprocess
import sys
import tempfile
import unittest
import threading
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "sync.py"
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import sync


def git(repo, *args):
    env = os.environ.copy()
    env["LC_ALL"] = "C.UTF-8"
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True,
        encoding="utf-8", capture_output=True, env=env,
    ).stdout.strip()


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.remote = base / "remote.git"
        self.repo = base / "repo"
        self.other = base / "other"
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

    def sync(self, *args, allow_dirty=False):
        env = os.environ.copy()
        env["LC_ALL"] = "C.UTF-8"
        env["PYTHONUTF8"] = "1"
        env["GIT_SYNC_TEST_DIRECT"] = "success"
        command = [sys.executable, str(SCRIPT), *args]
        if allow_dirty:
            command.insert(2, "--allow-dirty")
        return subprocess.run(
            command, cwd=self.repo,
            text=True, encoding="utf-8", capture_output=True, env=env,
        )

    def test_first_push_creates_upstream_and_uploads_commit(self):
        (self.repo / "README.md").write_text("首次同步\n", encoding="utf-8")
        result = self.sync("--message", "docs: 更新说明", "--", "README.md", allow_dirty=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "pushed")
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "@{upstream}"), "origin/main")
        clone = Path(self.temp.name) / "clone"
        subprocess.run(["git", "clone", str(self.remote), str(clone)], check=True, capture_output=True)
        self.assertEqual((clone / "README.md").read_text(encoding="utf-8"), "首次同步\n")

    def test_no_changes_does_not_create_empty_commit(self):
        before = git(self.repo, "rev-parse", "HEAD")
        result = self.sync("--message", "docs: 空提交", "--", "README.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "no_changes")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)

    def test_sensitive_path_is_not_committed(self):
        before = git(self.repo, "rev-parse", "HEAD")
        (self.repo / ".env").write_text("API_KEY=example\n", encoding="utf-8")
        result = self.sync("--message", "chore: 错误提交", "--", ".env")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "blocked_sensitive_path")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)

    def test_sensitive_file_inside_directory_is_blocked_before_staging(self):
        config = self.repo / "config"
        config.mkdir()
        (config / ".env").write_text("TOKEN=example\n", encoding="utf-8")
        (config / "settings.json").write_text("{}\n", encoding="utf-8")
        result = self.sync("--message", "chore: 不应暂存", "--", "config", allow_dirty=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "blocked_sensitive_path")
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")

    def test_missing_upstream_preserves_local_commit(self):
        git(self.repo, "remote", "remove", "origin")
        (self.repo / "README.md").write_text("仅本地\n", encoding="utf-8")
        result = self.sync("--message", "docs: 本地提交", "--", "README.md", allow_dirty=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "missing_upstream")
        self.assertEqual(git(self.repo, "log", "-1", "--pretty=%s"), "docs: 本地提交")

    def test_diverged_remote_does_not_overwrite_remote(self):
        self.sync("--message", "docs: 建立上游", "--", "README.md")
        subprocess.run(["git", "clone", str(self.remote), str(self.other)], check=True, capture_output=True)
        git(self.other, "config", "user.name", "其他用户")
        git(self.other, "config", "user.email", "other@example.com")
        (self.other / "remote.txt").write_text("远程新提交\n", encoding="utf-8")
        git(self.other, "add", "remote.txt")
        git(self.other, "commit", "-m", "docs: 远程更新")
        git(self.other, "push")
        (self.repo / "local.txt").write_text("本地新提交\n", encoding="utf-8")
        result = self.sync("--message", "docs: 本地更新", "--", "local.txt", allow_dirty=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "push_failed")
        self.assertEqual(git(self.other, "log", "-1", "--pretty=%s"), "docs: 远程更新")

    def test_paths_are_required(self):
        result = self.sync("--message", "docs: 无路径")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid_arguments")

    def test_auth_guidance_branches_by_platform(self):
        import git_platform
        self.assertIn("PowerShell", git_platform.auth_guidance("win32"))
        self.assertNotIn("PowerShell", git_platform.auth_guidance("darwin"))
        self.assertIn("gh auth login", git_platform.auth_guidance("linux"))

    def test_missing_git_is_reported_before_any_commit(self):
        before = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "README.md").write_text("缺少 git\n", encoding="utf-8")
        env = os.environ.copy()
        env["LC_ALL"] = "C.UTF-8"
        env["PYTHONUTF8"] = "1"
        env["GIT_SYNC_TEST_GIT_AVAILABLE"] = "0"
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--message", "docs: 不应提交", "--", "README.md",
            ],
            cwd=self.repo, text=True, encoding="utf-8",
            capture_output=True, env=env,
        )
        self.assertEqual(result.returncode, 8, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "missing_dependency")
        self.assertIn("git", report["error"])
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=self.repo,
            text=True, encoding="utf-8", capture_output=True, check=True,
        ).stdout
        self.assertEqual(status, " M README.md\n")

    def test_available_git_passes_dependency_gate(self):
        (self.repo / "README.md").write_text("git 可用\n", encoding="utf-8")
        env = os.environ.copy()
        env["LC_ALL"] = "C.UTF-8"
        env["PYTHONUTF8"] = "1"
        env["GIT_SYNC_TEST_DIRECT"] = "success"
        env["GIT_SYNC_TEST_GIT_AVAILABLE"] = "1"
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--message", "docs: 依赖闸门放行", "--allow-dirty", "--", "README.md",
            ],
            cwd=self.repo, text=True, encoding="utf-8",
            capture_output=True, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pushed")

    def test_preexisting_staged_changes_are_not_included(self):
        (self.repo / "user.txt").write_text("用户已暂存\n", encoding="utf-8")
        git(self.repo, "add", "user.txt")
        (self.repo / "task.txt").write_text("本任务\n", encoding="utf-8")
        result = self.sync("--message", "docs: 只提交任务", "--", "task.txt")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "preexisting_staged_changes")
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "user.txt")
        self.assertNotIn("task.txt", git(self.repo, "ls-files"))

    def test_dirty_task_file_requires_manual_separation(self):
        (self.repo / "README.md").write_text("用户先改\n", encoding="utf-8")
        result = self.sync("--message", "docs: 不应混合", "--", "README.md", allow_dirty=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "preexisting_dirty_paths")
        self.assertEqual((self.repo / "README.md").read_text(encoding="utf-8"), "用户先改\n")

    def test_custom_push_refspec_cannot_redirect_or_force_push(self):
        git(self.repo, "config", "push.default", "matching")
        result = self.sync("--message", "docs: 建立上游", "--", "README.md", allow_dirty=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        (self.repo / "README.md").write_text("只推 main\n", encoding="utf-8")
        result = self.sync("--message", "docs: 推送当前分支", "--", "README.md", allow_dirty=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(git(self.remote, "rev-parse", "main"), git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(git(self.remote, "for-each-ref", "--format=%(refname)", "refs/heads/other"), "")

    def test_first_push_ignores_force_and_redirect_configuration(self):
        git(self.repo, "config", "remote.origin.push", "+refs/heads/main:refs/heads/other")
        (self.repo / "README.md").write_text("只推 main\n", encoding="utf-8")
        result = self.sync("--message", "docs: 首次安全推送", "--", "README.md", allow_dirty=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(git(self.remote, "rev-parse", "main"), git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(git(self.remote, "for-each-ref", "--format=%(refname)", "refs/heads/other"), "")

    def test_first_push_cannot_overwrite_diverged_remote(self):
        git(self.repo, "config", "remote.origin.push", "+refs/heads/main:refs/heads/main")
        subprocess.run(["git", "clone", str(self.remote), str(self.other)], check=True, capture_output=True)
        git(self.other, "config", "user.name", "其他用户")
        git(self.other, "config", "user.email", "other@example.com")
        git(self.other, "commit", "--allow-empty", "-m", "docs: 远程独立提交")
        git(self.other, "push", "origin", "HEAD:main")
        remote_before = git(self.remote, "rev-parse", "main")
        (self.repo / "README.md").write_text("本地无共同历史\n", encoding="utf-8")
        result = self.sync("--message", "docs: 不应覆盖", "--", "README.md", allow_dirty=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "push_failed")
        self.assertEqual(git(self.remote, "rev-parse", "main"), remote_before)

    def test_authentication_failure_returns_setup_guidance_before_commit(self):
        before = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "remote", "set-url", "origin", str(Path(self.temp.name) / "missing.git"))
        (self.repo / "README.md").write_text("尚未登录\n", encoding="utf-8")
        result = self.sync("--message", "docs: 不应提前提交", "--", "README.md", allow_dirty=True)
        self.assertEqual(result.returncode, 6)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "authentication_required")
        self.assertIn("gh auth login", report["setup"])
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")
        self.assertEqual(
            (self.repo / "README.md").read_text(encoding="utf-8"), "尚未登录\n"
        )

    def test_proxy_failure_returns_proxy_troubleshooting(self):
        server = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            git(self.repo, "remote", "set-url", "origin", f"http://127.0.0.1:{server.server_port}/repo.git")
        finally:
            server.server_close()
        git(self.repo, "config", "http.proxy", "http://127.0.0.1:1")
        (self.repo / "README.md").write_text("代理未启动\n", encoding="utf-8")
        result = self.sync("--message", "docs: 代理测试", "--", "README.md", allow_dirty=True)
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "proxy_error")
        self.assertIn("127.0.0.1:1", report["setup"])
        # 执行器是独立子进程，这里无法 mock 端口探测；运行机器若有代理在监听会走替代端口分支。
        # 两个分支的文案都含推送命令前缀，具体分支由 ProxyPortProbeTests 的 mock 单测确定性覆盖。
        self.assertIn("git -c http.proxy=", report["setup"])

    def test_common_private_key_names_are_blocked(self):
        for name in ("id_rsa", "id_ed25519", ".netrc"):
            with self.subTest(name=name):
                (self.repo / name).write_text("测试占位，不是真实凭据\n", encoding="utf-8")
                result = self.sync("--message", "chore: 不应提交", "--", name, allow_dirty=True)
                self.assertEqual(json.loads(result.stdout)["status"], "blocked_sensitive_path")
                self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")

    def test_deletion_is_committed_and_pushed(self):
        result = self.sync("--message", "docs: 删除说明", "--", "README.md", allow_dirty=True)
        (self.repo / "README.md").unlink()
        result = self.sync("--message", "docs: 删除说明", "--", "README.md", allow_dirty=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pushed")
        self.assertEqual(git(self.repo, "log", "-1", "--pretty=%s"), "docs: 删除说明")

    def test_error_output_redacts_embedded_credentials(self):
        git(self.repo, "remote", "set-url", "origin", "https://user:secret-token@example.invalid/repo.git")
        (self.repo / "README.md").write_text("触发错误\n", encoding="utf-8")
        result = self.sync("--message", "docs: 触发错误", "--", "README.md", allow_dirty=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("secret-token", result.stdout)
        self.assertNotIn("secret-token", result.stderr)

    def test_integration_reports_space_filename_without_quotes(self):
        (self.repo / "task file.txt").write_text("本任务\n", encoding="utf-8")
        result = self.sync("--message", "docs: 空格文件名", "--", "task file.txt", allow_dirty=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pushed")

    def test_real_python_config_is_blocked_integration(self):
        (self.repo / "settings.py").write_text(
            'DEBUG = False\nAPI_KEY = "ghp_realvalue1234567890abcdef"\n',
            encoding="utf-8",
        )
        result = self.sync("--message", "feat: 普通文件藏密钥", "--", "settings.py", allow_dirty=True)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked_sensitive_path")
        self.assertIn("settings.py", report["paths"])
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")

    def test_env_example_template_is_allowed_integration(self):
        (self.repo / ".env.example").write_text("API_KEY=your-api-key-here\n", encoding="utf-8")
        result = self.sync("--message", "docs: 配置模板", "--", ".env.example", allow_dirty=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pushed")

    def test_push_stage_failure_keeps_local_commit(self):
        self.sync("--message", "docs: 先建立 upstream", "--", "README.md", allow_dirty=True)
        (self.repo / "README.md").write_text("推送时远程失败\n", encoding="utf-8")

        class OneShotProxyHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()

            def do_POST(self):
                self.send_response(502)
                self.end_headers()
                self.wfile.write(b"Failed to connect over proxy 127.0.0.1")

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), OneShotProxyHandler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        git(self.repo, "remote", "set-url", "origin", f"http://127.0.0.1:{port}/repo.git")
        git(self.repo, "config", "http.proxy", "")
        git(self.repo, "config", "https.proxy", "")
        git(self.repo, "config", "http.proxy", f"http://127.0.0.1:{port}")
        try:
            result = self.sync("--message", "docs: 推送失败", "--", "README.md", allow_dirty=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertIn(report["status"], ("push_failed", "proxy_error", "remote_unavailable"))
        self.assertIn("commit", report)
        self.assertEqual(git(self.repo, "log", "-1", "--pretty=%s"), "docs: 推送失败")

    def test_push_stage_auth_failure_keeps_local_commit(self):
        class WriteFailsHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"")

            def do_POST(self):
                self.send_response(500)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), WriteFailsHandler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        git(self.repo, "remote", "set-url", "origin", f"http://127.0.0.1:{port}/repo.git")
        git(self.repo, "config", "http.proxy", "")
        git(self.repo, "config", "https.proxy", "")
        (self.repo / "README.md").write_text("推送时权限失效\n", encoding="utf-8")
        try:
            result = self.sync("--message", "docs: 权限失败", "--", "README.md", allow_dirty=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertIn(report["status"], ("push_failed", "authentication_required", "remote_unavailable"))
        self.assertIn("commit", report)
        self.assertEqual(git(self.repo, "log", "-1", "--pretty=%s"), "docs: 权限失败")


class NetworkArgTests(unittest.TestCase):
    def make_args(self, **overrides):
        import argparse
        defaults = {
            "retry_direct": False,
            "proxy": None,
            "remember_proxy": False,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_remember_proxy_requires_proxy_value(self):
        error = sync.validate_network_args(self.make_args(remember_proxy=True))
        self.assertIsNotNone(error)
        self.assertIn("--proxy", error)

    def test_retry_direct_and_proxy_are_mutually_exclusive(self):
        error = sync.validate_network_args(
            self.make_args(retry_direct=True, proxy="http://127.0.0.1:7890")
        )
        self.assertIsNotNone(error)
        self.assertIn("互斥", error)

    def test_valid_combinations_pass(self):
        self.assertIsNone(sync.validate_network_args(self.make_args()))
        self.assertIsNone(
            sync.validate_network_args(self.make_args(proxy="http://127.0.0.1:7890"))
        )
        self.assertIsNone(
            sync.validate_network_args(
                self.make_args(proxy="http://127.0.0.1:7890", remember_proxy=True)
            )
        )
        self.assertIsNone(
            sync.validate_network_args(self.make_args(retry_direct=True))
        )

    def test_cli_args_override_env_in_merged_network_env(self):
        args = self.make_args(
            proxy="http://127.0.0.1:7890", remember_proxy=True,
        )
        merged = sync.build_network_env(
            args,
            base_env={
                "GIT_SYNC_PROXY": "http://env.invalid:1",
                "GIT_SYNC_REMEMBER_PROXY": "0",
                "KEEP_ME": "保留",
            },
        )
        self.assertEqual(merged["GIT_SYNC_PROXY"], "http://127.0.0.1:7890")
        self.assertEqual(merged["GIT_SYNC_REMEMBER_PROXY"], "1")
        self.assertEqual(merged["KEEP_ME"], "保留")

    def test_env_is_kept_when_cli_arg_absent(self):
        merged = sync.build_network_env(
            self.make_args(),
            base_env={"GIT_SYNC_PROXY": "http://env.invalid:1"},
        )
        self.assertEqual(merged["GIT_SYNC_PROXY"], "http://env.invalid:1")


class TimeoutConfigTests(unittest.TestCase):
    def test_default_timeout_is_30_seconds(self):
        self.assertEqual(sync.resolve_timeout({}), 30)

    def test_valid_env_override_is_used(self):
        self.assertEqual(sync.resolve_timeout({"GIT_SYNC_TIMEOUT": "60"}), 60)

    def test_invalid_values_fall_back_to_default(self):
        for bad in ("0", "-5", "abc", ""):
            with self.subTest(bad=bad):
                self.assertEqual(sync.resolve_timeout({"GIT_SYNC_TIMEOUT": bad}), 30)


class ErrorClassificationTests(unittest.TestCase):
    def test_remote_missing_is_not_authentication(self):
        samples = [
            "fatal: repository 'https://github.com/zyx1216/missing.git/' not found",
            "fatal: remote error: Repository not found.",
            "ERROR: Repository not found",
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assertEqual(sync.classify_remote_error(text), "remote_unavailable")

    def test_authentication_failures_are_detected(self):
        samples = [
            "fatal: Authentication failed for 'https://github.com/o/r.git/'",
            "remote: Permission to zyx1216/r.git denied to other-user.",
            "git@github.com: Permission denied (publickey).",
            "fatal: unable to access: The requested URL returned error: 403",
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assertEqual(sync.classify_remote_error(text), "authentication_required")

    def test_proxy_failures_are_detected(self):
        text = "fatal: unable to access: Failed to connect over proxy 127.0.0.1 port 1"
        self.assertEqual(
            sync.classify_remote_error(text, configured_proxy="http://127.0.0.1:1"),
            "proxy_error",
        )

    def test_direct_failure_without_proxy_is_remote_unavailable(self):
        text = "fatal: unable to access 'https://github.com/o/r.git/': Failed to connect to github.com:443: Could not connect to server"
        self.assertEqual(sync.classify_remote_error(text, configured_proxy=""), "remote_unavailable")
        proxy_text = "fatal: unable to access: Failed to connect to github.com:443 over proxy 127.0.0.1: Could not connect to server"
        self.assertEqual(
            sync.classify_remote_error(proxy_text, configured_proxy="http://127.0.0.1:20890"),
            "proxy_error",
        )

    def test_unknown_error_falls_back_to_remote_unavailable(self):
        self.assertEqual(sync.classify_remote_error("some strange git failure"), "remote_unavailable")


class PorcelainPathTests(unittest.TestCase):
    def test_plain_status_with_spaces_and_chinese(self):
        raw = " D old name.txt\0?? 中文 文件.txt\0"
        self.assertEqual(
            sync.parse_porcelain_paths(raw),
            ["old name.txt", "中文 文件.txt"],
        )

    def test_rename_returns_both_source_and_target(self):
        raw = "R  old name.txt\0new name.txt\0 M tracked file.txt\0"
        self.assertEqual(
            sync.parse_porcelain_paths(raw),
            ["old name.txt", "new name.txt", "tracked file.txt"],
        )

    def test_empty_output_means_no_paths(self):
        self.assertEqual(sync.parse_porcelain_paths(""), [])


class ContentSecretTests(unittest.TestCase):
    def test_assigned_secret_in_added_line_is_detected(self):
        diff = "@@\n+API_KEY=ghp_realvalue1234567890\n normal line\n"
        hits = sync.find_secret_lines(diff)
        self.assertEqual(hits, ["API_KEY=ghp_realvalue1234567890"])

    def test_removed_secret_line_is_ignored(self):
        diff = "@@\n-API_KEY=oldvalue\n"
        self.assertEqual(sync.find_secret_lines(diff), [])

    def test_placeholder_values_are_allowed(self):
        for line in (
            "+API_KEY=your-api-key-here",
            '+token = "<your-token>"',
            "+password=${DB_PASSWORD}",
        ):
            with self.subTest(line=line):
                self.assertEqual(sync.find_secret_lines(f"@@\n{line}\n"), [])


class ProxyPortProbeTests(unittest.TestCase):
    def test_reports_only_listening_loopback_ports(self):
        server = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
        port = server.server_port
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            open_ports = sync.detect_open_proxy_ports([port, 1], timeout=1)
        finally:
            server.server_close()
            thread.join(timeout=2)
        self.assertIn(port, open_ports)
        self.assertNotIn(1, open_ports)

    def test_default_candidate_list_covers_common_ports(self):
        self.assertIn(20890, sync.DEFAULT_PROXY_PORTS)
        self.assertIn(20891, sync.DEFAULT_PROXY_PORTS)
        self.assertIn(7890, sync.DEFAULT_PROXY_PORTS)

    def test_guidance_suggests_listening_alternative_port(self):
        server = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
        port = server.server_port
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        original = sync.detect_open_proxy_ports
        sync.detect_open_proxy_ports = lambda *args, **kwargs: [port]
        try:
            guidance = sync.build_proxy_guidance("http://127.0.0.1:20890")
        finally:
            sync.detect_open_proxy_ports = original
            server.server_close()
            thread.join(timeout=2)
        self.assertIn(f"127.0.0.1:{port}", guidance)
        self.assertIn("git -c http.proxy=", guidance)

    def test_guidance_without_open_port_offers_direct_bypass(self):
        original = sync.detect_open_proxy_ports
        sync.detect_open_proxy_ports = lambda *args, **kwargs: []
        try:
            guidance = sync.build_proxy_guidance("http://127.0.0.1:20890")
        finally:
            sync.detect_open_proxy_ports = original
        self.assertIn("git -c http.proxy= -c https.proxy= push", guidance)


if __name__ == "__main__":
    unittest.main()
