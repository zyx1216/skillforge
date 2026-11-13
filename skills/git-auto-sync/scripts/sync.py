#!/usr/bin/env python3
import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path, PurePath

import network_adapter
import git_platform


SENSITIVE_NAMES = {
    ".env", ".netrc", "credentials.json", "secrets.yml", "secrets.yaml",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".jks", ".pfx", ".keystore")
CREDENTIAL_URL = re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)
ASSIGNED_SECRET = re.compile(
    r"(?i)\b(password|passwd|token|api[_-]?key|secret|access[_-]?key)\b(\s*[:=]\s*)([^\s]+)"
)
PLACEHOLDER_VALUE = re.compile(
    r"^(?:\")?(?:<[^>]+>|\$\{[^}]+\}|[a-z0-9_]*(?:your|placeholder|example|sample|change[_-]?me|dummy|test)[a-z0-9_.-]*)(?:\")?$",
    re.IGNORECASE,
)
AUTH_ERROR = re.compile(
    r"authentication|permission denied|access denied|could not read|"
    r"invalid username|403|401|denied",
    re.IGNORECASE,
)
REPO_MISSING = re.compile(r"repository .*not found|remote error: repository not found", re.IGNORECASE)
PROXY_ERROR = re.compile(r"proxy|Failed to connect", re.IGNORECASE)
SETUP_GUIDANCE = git_platform.auth_guidance()


def dependency_check(env=None):
    """测试通过 GIT_SYNC_TEST_GIT_AVAILABLE 注入，避免依赖运行机器状态。"""
    env = env if env is not None else os.environ
    test_value = env.get("GIT_SYNC_TEST_GIT_AVAILABLE")
    if test_value is not None:
        if test_value == "1":
            return None
        return {
            "status": "missing_dependency",
            "error": "未在 PATH 中找到可用的 git，请先安装 Git 并确认 git --version 能正常输出",
        }
    return git_platform.check_dependencies()

DEFAULT_TIMEOUT = 30
DEFAULT_PROXY_PORTS = (7890, 7897, 10808, 10809, 20890, 20891, 8080, 1080)


def resolve_timeout(env):
    raw = (env.get("GIT_SYNC_TIMEOUT") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def detect_open_proxy_ports(candidates=DEFAULT_PROXY_PORTS, timeout=0.3):
    """只探测本机回环地址，返回当前在监听的候选端口，不做任何外网连接。"""
    listening = []
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            if sock.connect_ex(("127.0.0.1", int(port))) == 0:
                listening.append(int(port))
    return listening


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


NETWORK_EXIT_CODE = 7
DEPENDENCY_EXIT_CODE = 8


def evaluate_network(env=None):
    """提交前跑连接状态机，返回需要停下的报告；直连或可用代理返回 None。"""
    decision = network_adapter.decide_network_action(env if env is not None else os.environ)
    outcome = decision["outcome"]
    if outcome == "direct":
        return None
    if outcome in ("use_provided_proxy", "use_saved_proxy"):
        return decision
    if outcome == "direct_unavailable":
        return report(
            "direct_unavailable", NETWORK_EXIT_CODE,
            error="两轮直连重试均失败，当前窗口直连 GitHub 不可用",
            diagnostics=decision["diagnostics"], reasons=decision["reasons"],
        )
    return report(
        "network_choice_required", NETWORK_EXIT_CODE,
        error="直连 GitHub 连续失败，需要用户决定继续直连还是提供代理",
        diagnostics=decision["diagnostics"], reasons=decision["reasons"],
    )


def proxy_git_args(proxy_url):
    """把一次性代理用 -c 注入，不改全局 gitconfig。"""
    if not proxy_url:
        return []
    return ["-c", f"http.proxy={proxy_url}", "-c", f"https.proxy={proxy_url}"]


def sanitize(text):
    text = CREDENTIAL_URL.sub(r"\1<已隐藏>@", text)
    return ASSIGNED_SECRET.sub(r"\1\2<已隐藏>", text)


def classify_remote_error(error, configured_proxy=""):
    """只做错误归类，不执行任何 Git 写操作，预检和 push 失败共用。"""
    if REPO_MISSING.search(error):
        return "remote_unavailable"
    if AUTH_ERROR.search(error):
        return "authentication_required"
    if configured_proxy and re.search(r"proxy", error, re.IGNORECASE):
        return "proxy_error"
    return "remote_unavailable"


def is_sensitive(path):
    name = PurePath(path).name.lower()
    if name in SENSITIVE_NAMES or name.startswith(".env."):
        return name not in {".env.example", ".env.template", ".env.sample"}
    return name.endswith(SENSITIVE_SUFFIXES) or name.endswith(".secret")


def parse_porcelain_paths(raw):
    """解析 git status --porcelain -z 的 NUL 分隔输出。

    普通记录是"状态+空格+路径"；重命名(R)和复制(C)记录后面多跟一段源路径。
    """
    records = [part for part in raw.split("\0") if part]
    paths = []
    index = 0
    while index < len(records):
        record = records[index]
        status = record[:2]
        paths.append(record[3:])
        if status[0] in ("R", "C"):
            index += 1
            paths.append(records[index])
        index += 1
    return paths


def find_secret_lines(diff_text):
    """只检查暂存 diff 中的新增行，返回疑似含密钥的明文行。"""
    hits = []
    for line in diff_text.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for match in ASSIGNED_SECRET.finditer(line):
            value = match.group(3).strip().strip('"').strip("'")
            if value and not PLACEHOLDER_VALUE.match(value):
                hits.append(line[1:].strip())
                break
    return hits


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


def preflight_remote(remote_name, remote_branch, proxy_args=None):
    proxy_args = proxy_args or []
    probe = run_git([*proxy_args, "ls-remote", "--heads", remote_name, remote_branch], check=False)
    if probe.returncode == 0:
        return None
    error = sanitize(probe.stderr.strip())
    configured_proxy = run_git(["config", "--get", "http.proxy"], check=False).stdout.strip()
    kind = classify_remote_error(error, configured_proxy=configured_proxy)
    if kind == "authentication_required":
        return report("authentication_required", 6, error=error, setup=SETUP_GUIDANCE)
    if kind == "proxy_error":
        setup = build_proxy_guidance(configured_proxy)
        return report("proxy_error", 2, error=error, proxy=configured_proxy, setup=setup)
    return report("remote_unavailable", 2, error=error or "无法访问远程仓库")


def classify_push_failure(error):
    """push 失败时归类。调用方已生成 commit，这里只返回报告，不做任何回滚。"""
    clean_error = sanitize(error)
    configured_proxy = run_git(["config", "--get", "http.proxy"], check=False).stdout.strip()
    kind = classify_remote_error(clean_error, configured_proxy=configured_proxy)
    commit = run_git(["rev-parse", "HEAD"]).stdout.strip()
    if kind == "authentication_required":
        return report(
            "authentication_required", 6, commit=commit,
            error=clean_error, setup=SETUP_GUIDANCE,
        )
    if kind == "proxy_error":
        setup = build_proxy_guidance(configured_proxy)
        return report(
            "proxy_error", 2, commit=commit,
            error=clean_error, proxy=configured_proxy, setup=setup,
        )
    return report("push_failed", 4, commit=commit, error=clean_error)


def build_proxy_guidance(configured_proxy):
    listening = detect_open_proxy_ports()
    configured_port = re.search(r":(\d+)", configured_proxy or "")
    configured_port = int(configured_port.group(1)) if configured_port else None
    alternatives = [port for port in listening if port != configured_port]
    base = (
        f"当前 Git HTTP 代理为 {configured_proxy}，连接失败。请先启动代理软件并核对端口。"
        "Codex 不会自动绕过或修改你的代理。"
    )
    if alternatives:
        port = alternatives[0]
        base += (
            f"检测到本机回环端口 {port} 正在监听，若它是你的代理端口，可仅本次指定它推送："
            f"git -c http.proxy=http://127.0.0.1:{port} "
            f"-c https.proxy=http://127.0.0.1:{port} push。"
        )
    else:
        base += (
            "没有探测到常见代理端口在监听。确认当前网络可直连 GitHub 时，"
            "可仅本次绕过代理：git -c http.proxy= -c https.proxy= push。"
        )
    return base


def parse_args():
    parser = argparse.ArgumentParser(description="提交指定路径并推送当前分支 upstream")
    parser.add_argument("--message", required=True, help="Codex 根据实际改动生成的提交说明")
    parser.add_argument("--allow-dirty", action="store_true", help="确认路径中的改动均由本任务产生")
    parser.add_argument("--retry-direct", action="store_true", help="三败后再做一轮直连重试")
    parser.add_argument("--proxy", default=None, help="三败后本轮使用的代理地址")
    parser.add_argument("--remember-proxy", action="store_true", help="同时记住 --proxy 给的代理，供以后兜底")
    parser.add_argument("paths", nargs="*", help="只暂存这些仓库相对路径")
    return parser.parse_args()


def validate_network_args(args):
    """校验网络重跑参数的组合，返回错误信息；合法时返回 None。"""
    if args.remember_proxy and not args.proxy:
        return "--remember-proxy 必须和 --proxy 一起使用，不能单独记住代理"
    if args.retry_direct and args.proxy:
        return "--retry-direct 和 --proxy 互斥，继续直连和提供代理只能二选一"
    return None


def build_network_env(args, base_env=None):
    """命令行参数优先于旧环境变量，合并出状态机读取的环境。"""
    env = dict(base_env if base_env is not None else os.environ)
    if args.retry_direct:
        env["GIT_SYNC_RETRY_DIRECT"] = "1"
    if args.proxy:
        env["GIT_SYNC_PROXY"] = args.proxy
    if args.remember_proxy:
        env["GIT_SYNC_REMEMBER_PROXY"] = "1"
    return env


def unstage_task_paths(paths):
    """中止时只把本次 add 的路径移出暂存区。

    进入提交流程前的预暂存检查已确认索引为空，所以这里的 reset 不会碰到
    用户原有暂存；它只影响索引，工作区文件原样保留。
    """
    run_git(["reset", "--", *paths])


def main():
    args = parse_args()
    if not args.paths or not args.message.strip():
        return report("invalid_arguments", 2, error="必须提供提交说明和至少一个路径")
    if any(PurePath(path).is_absolute() or ".." in PurePath(path).parts for path in args.paths):
        return report("invalid_arguments", 2, error="路径必须是仓库内的相对路径")
    network_arg_error = validate_network_args(args)
    if network_arg_error is not None:
        return report("invalid_arguments", 2, error=network_arg_error)
    sensitive = [path for path in args.paths if is_sensitive(path)]
    if sensitive:
        return report("blocked_sensitive_path", 3, paths=sensitive)
    missing = dependency_check()
    if missing is not None:
        return report(missing["status"], DEPENDENCY_EXIT_CODE, error=missing["error"])
    try:
        run_git(["rev-parse", "--show-toplevel"])
        preexisting_staged = run_git(["diff", "--cached", "--name-only"], check=False)
        if preexisting_staged.returncode != 0:
            return report("git_error", 1, error="无法读取暂存区")
        if preexisting_staged.stdout.strip():
            return report("preexisting_staged_changes", 5, error="请先处理已有暂存内容，执行器不会保存或重写用户索引")
        porcelain = run_git(["status", "--porcelain", "-z", "--", *args.paths]).stdout
        dirty_paths = parse_porcelain_paths(porcelain)
        if dirty_paths and not args.allow_dirty:
            return report("preexisting_dirty_paths", 5, paths=dirty_paths)
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
        staged_diff = run_git(["diff", "--cached", "-U0", "--", *staged]).stdout
        secret_hits = find_secret_lines(staged_diff)
        if secret_hits:
            run_git(["reset", "--", *args.paths])
            return report(
                "blocked_sensitive_path", 3,
                paths=staged, findings=secret_hits,
                error="暂存改动的新增行疑似包含密钥，已回滚暂存且未提交",
            )
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
        decision = evaluate_network(env=build_network_env(args))
        if isinstance(decision, int):
            unstage_task_paths(args.paths)
            return decision
        proxy_url = decision["proxy_url"] if decision else None
        proxy_args = proxy_git_args(proxy_url)
        blocked = preflight_remote(remote_name, remote_branch, proxy_args=proxy_args)
        if blocked is not None:
            unstage_task_paths(args.paths)
            return blocked
        run_git(["commit", "-m", args.message])
        commit = run_git(["rev-parse", "HEAD"]).stdout.strip()
        if first_push:
            push = run_git([
                *proxy_args,
                "push", "-u", "origin", f"refs/heads/{branch}:refs/heads/{branch}",
            ], check=False)
            if push.returncode != 0:
                return classify_push_failure(push.stderr.strip() or push.stdout.strip())
            return report("pushed", 0, commit=commit, upstream=f"origin/{branch}")
        push = run_git([
            *proxy_args, "push", remote_name,
            f"refs/heads/{branch}:refs/heads/{remote_branch}",
        ], check=False)
        if push.returncode != 0:
            return classify_push_failure(push.stderr.strip() or push.stdout.strip())
        return report("pushed", 0, commit=commit, upstream=upstream_name)
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        return report("git_error", 1, error=sanitize(str(error)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
