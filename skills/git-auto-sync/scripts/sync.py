#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePath


SENSITIVE_NAMES = {
    ".env", ".netrc", "credentials.json", "secrets.yml", "secrets.yaml",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".jks", ".pfx", ".keystore")
CREDENTIAL_URL = re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)
ASSIGNED_SECRET = re.compile(
    r"(?i)\b(password|passwd|token|api[_-]?key|secret|access[_-]?key)\b(\s*[:=]\s*)([^\s]+)"
)
AUTH_ERROR = re.compile(
    r"authentication|permission denied|access denied|could not read|"
    r"invalid username|repository not found|not found|403|401",
    re.IGNORECASE,
)
PROXY_ERROR = re.compile(r"proxy|Failed to connect", re.IGNORECASE)
SETUP_GUIDANCE = (
    "GitHub 凭据未配置、已失效或当前账号无权访问远程。请打开 Windows PowerShell"
    "（Win+R 输入 powershell），不要在 Codex 对话框发送命令，也无需进入项目目录。"
    "先执行 gh auth login，按提示选择 GitHub.com、HTTPS 和浏览器登录；"
    "成功后回到同一个 PowerShell 窗口执行 gh auth setup-git，再用 gh auth status 检查；"
    "使用 SSH 时改为配置本机 SSH 密钥并用 ssh -T git@github.com 验证。"
    "不要把密码或 Token 发给 Codex。配置后重新运行本任务。"
)

DEFAULT_TIMEOUT = 30


def resolve_timeout(env):
    raw = (env.get("GIT_SYNC_TIMEOUT") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def report(status, exit_code, **details):
    print(json.dumps({"status": status, **details}, ensure_ascii=False))
    return exit_code


def run_git(args, check=True):
    env = os.environ.copy()
    env["LC_ALL"] = "C.UTF-8"
    result = subprocess.run(
        ["git", *args], text=True, encoding="utf-8",
        capture_output=True, timeout=resolve_timeout(env), env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result


def sanitize(text):
    text = CREDENTIAL_URL.sub(r"\1<已隐藏>@", text)
    return ASSIGNED_SECRET.sub(r"\1\2<已隐藏>", text)


def is_sensitive(path):
    name = PurePath(path).name.lower()
    if name in SENSITIVE_NAMES or name.startswith(".env."):
        return name not in {".env.example", ".env.template", ".env.sample"}
    return name.endswith(SENSITIVE_SUFFIXES) or name.endswith(".secret")


def resolve_push_target():
    branch = run_git(["branch", "--show-current"]).stdout.strip()
    if not branch:
        return None
    upstream = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], check=False)
    if upstream.returncode == 0:
        remote_name = run_git(["config", f"branch.{branch}.remote"], check=False).stdout.strip()
        merge_ref = run_git(["config", f"branch.{branch}.merge"], check=False).stdout.strip()
        if remote_name and merge_ref.startswith("refs/heads/"):
            return remote_name, merge_ref.removeprefix("refs/heads/"), branch, upstream.stdout.strip(), False
        return None
    if run_git(["remote"]).stdout.splitlines() == ["origin"]:
        return "origin", branch, branch, f"origin/{branch}", True
    return None


def preflight_remote(remote_name, remote_branch):
    probe = run_git(["ls-remote", "--heads", remote_name, remote_branch], check=False)
    if probe.returncode == 0:
        return None
    error = sanitize(probe.stderr.strip())
    if AUTH_ERROR.search(error):
        return report("authentication_required", 6, error=error, setup=SETUP_GUIDANCE)
    configured_proxy = run_git(["config", "--get", "http.proxy"], check=False).stdout.strip()
    if configured_proxy and PROXY_ERROR.search(error):
        setup = (
            f"当前 Git HTTP 代理为 {configured_proxy}，连接失败。请先启动代理软件并核对端口；"
            "如果你知道当前网络可以直连 GitHub，可在项目目录的 PowerShell 中仅本次绕过代理："
            "git -c http.proxy= -c https.proxy= push。"
            "该命令不修改全局配置。Codex 不会自动绕过或修改你的代理。"
        )
        return report("proxy_error", 2, error=error, proxy=configured_proxy, setup=setup)
    return report("remote_unavailable", 2, error=error or "无法访问远程仓库")


def parse_args():
    parser = argparse.ArgumentParser(description="提交指定路径并推送当前分支 upstream")
    parser.add_argument("--message", required=True, help="Codex 根据实际改动生成的提交说明")
    parser.add_argument("--allow-dirty", action="store_true", help="确认路径中的改动均由本任务产生")
    parser.add_argument("paths", nargs="*", help="只暂存这些仓库相对路径")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.paths or not args.message.strip():
        return report("invalid_arguments", 2, error="必须提供提交说明和至少一个路径")
    if any(PurePath(path).is_absolute() or ".." in PurePath(path).parts for path in args.paths):
        return report("invalid_arguments", 2, error="路径必须是仓库内的相对路径")
    sensitive = [path for path in args.paths if is_sensitive(path)]
    if sensitive:
        return report("blocked_sensitive_path", 3, paths=sensitive)
    try:
        run_git(["rev-parse", "--show-toplevel"])
        preexisting_staged = run_git(["diff", "--cached", "--name-only"], check=False)
        if preexisting_staged.returncode != 0:
            return report("git_error", 1, error="无法读取暂存区")
        if preexisting_staged.stdout.strip():
            return report("preexisting_staged_changes", 5, error="请先处理已有暂存内容，执行器不会保存或重写用户索引")
        dirty_paths = run_git(["status", "--porcelain", "--", *args.paths]).stdout.splitlines()
        if dirty_paths and not args.allow_dirty:
            return report("preexisting_dirty_paths", 5, paths=[line[3:] for line in dirty_paths])
        candidates = run_git([
            "ls-files", "--cached", "--others", "--deleted", "--modified",
            "--exclude-standard", "--", *args.paths,
        ]).stdout.splitlines()
        sensitive_candidates = [path for path in candidates if is_sensitive(path)]
        if sensitive_candidates:
            return report("blocked_sensitive_path", 3, paths=sensitive_candidates)
        run_git(["add", "--", *args.paths])
        staged = run_git(["diff", "--cached", "--name-only"]).stdout.splitlines()
        sensitive_staged = [path for path in staged if is_sensitive(path)]
        if sensitive_staged:
            run_git(["reset", "--", *args.paths])
            return report("blocked_sensitive_path", 3, paths=sensitive_staged)
        if not staged:
            return report("no_changes", 0)
        if run_git(["diff", "--cached", "--quiet"], check=False).returncode == 0:
            return report("no_changes", 0)
        target = resolve_push_target()
        if target is None:
            run_git(["commit", "-m", args.message])
            commit = run_git(["rev-parse", "HEAD"]).stdout.strip()
            return report("missing_upstream", 2, commit=commit, error="没有可安全确定的当前分支 upstream")
        remote_name, remote_branch, branch, upstream_name, first_push = target
        blocked = preflight_remote(remote_name, remote_branch)
        if blocked is not None:
            return blocked
        run_git(["commit", "-m", args.message])
        commit = run_git(["rev-parse", "HEAD"]).stdout.strip()
        if first_push:
            push = run_git([
                "push", "-u", "origin", f"refs/heads/{branch}:refs/heads/{branch}",
            ], check=False)
            if push.returncode != 0:
                return report("push_failed", 4, commit=commit, error=sanitize(push.stderr.strip()))
            return report("pushed", 0, commit=commit, upstream=f"origin/{branch}")
        push = run_git(["push", remote_name, f"refs/heads/{branch}:refs/heads/{remote_branch}"], check=False)
        if push.returncode != 0:
            return report("push_failed", 4, commit=commit, error=sanitize(push.stderr.strip()))
        return report("pushed", 0, commit=commit, upstream=upstream_name)
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        return report("git_error", 1, error=sanitize(str(error)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
