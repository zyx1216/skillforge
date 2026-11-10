"""连接状态机和 sync.py 之间的适配层。

线上用真实 socket、Windows 注册表和本地状态文件；测试通过 GIT_SYNC_TEST_*
环境变量注入结果，子进程里也能完全离线、无 flaky。
"""
import connection
import network
import proxy_pref


def _test_direct_probe(env):
    mode = env.get("GIT_SYNC_TEST_DIRECT")
    if mode is None:
        return None
    if mode == "success":
        return lambda: connection.DirectPorts(True, True)
    if mode == "fail":
        return lambda: connection.DirectPorts(False, False)
    if mode == "443_blocked_22_open":
        return lambda: connection.DirectPorts(False, True)
    return None


def _test_system_proxy(env):
    mode = env.get("GIT_SYNC_TEST_SYSTEM_PROXY")
    if mode == "residual":
        return connection.SystemProxyInfo("127.0.0.1", 7890, False, True)
    if mode == "node":
        return connection.SystemProxyInfo("127.0.0.1", 7890, True, False)
    return None


def _test_sleep(env):
    if "GIT_SYNC_TEST_DIRECT" in env:
        return lambda _: None
    return None


def _git_proxy_config(env):
    test_value = env.get("GIT_SYNC_TEST_GIT_PROXY")
    if test_value is not None:
        return {"http_proxy": test_value or None, "https_proxy": test_value or None}
    import subprocess

    def read(key):
        result = subprocess.run(
            ["git", "config", "--get", key],
            capture_output=True, text=True, encoding="utf-8",
        )
        value = result.stdout.strip()
        return value or None

    config = {
        "http_proxy": read("http.proxy"),
        "https_proxy": read("https.proxy"),
    }
    return config if any(config.values()) else None


def build_policy(env):
    test_probe = _test_direct_probe(env)
    if test_probe is not None:
        direct_probe = test_probe
    else:
        def direct_probe():
            return network.check_github_direct()

    test_alive = env.get("GIT_SYNC_TEST_PROXY_ALIVE")
    if test_alive is not None:
        proxy_port_probe = lambda url: test_alive == "1"
    else:
        def proxy_port_probe(proxy_url):
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            if not parsed.hostname or not parsed.port:
                return False
            return network.tcp_reachable(parsed.hostname, parsed.port, timeout=1)

    test_tunnel = env.get("GIT_SYNC_TEST_TUNNEL")
    if test_tunnel is not None:
        proxy_tunnel_probe = lambda url: test_tunnel == "1"
    elif "GIT_SYNC_TEST_DIRECT" in env:
        proxy_tunnel_probe = lambda url: True
    else:
        proxy_tunnel_probe = None

    saved_proxy = env.get("GIT_SYNC_TEST_SAVED_PROXY")
    if saved_proxy is None and "GIT_SYNC_TEST_DIRECT" not in env:
        preference = proxy_pref.load_preference(home=proxy_pref.home_from_env(env))
        saved_proxy = preference.proxy_url if preference else None

    system_proxy = _test_system_proxy(env)
    if system_proxy is None and "GIT_SYNC_TEST_DIRECT" not in env:
        status = network.detect_system_proxy()
        if status is not None:
            system_proxy = connection.SystemProxyInfo(
                status.host, status.port, status.port_listening, status.residual,
            )

    return connection.ConnectionPolicy(
        direct_probe=direct_probe,
        proxy_port_probe=proxy_port_probe,
        saved_proxy=saved_proxy,
        system_proxy=system_proxy,
        remember=env.get("GIT_SYNC_REMEMBER_PROXY") == "1",
        provided_proxy=env.get("GIT_SYNC_PROXY"),
        retry_direct=env.get("GIT_SYNC_RETRY_DIRECT") == "1",
        sleep=_test_sleep(env),
        git_proxy=_git_proxy_config(env),
        env_proxy=network.read_env_proxies(env),
        proxy_tunnel_probe=proxy_tunnel_probe,
    )


def decide_network_action(env):
    if env.get("GIT_SYNC_NETWORK_STATE") == "0":
        return {"outcome": "direct", "proxy_url": None, "should_save": False,
                "diagnostics": {}, "reasons": []}
    policy = build_policy(env)
    decision = connection.plan_connection(policy)
    result = {
        "outcome": decision.outcome,
        "proxy_url": decision.proxy_url,
        "should_save": decision.should_save,
        "diagnostics": decision.diagnostics,
        "reasons": decision.reasons,
    }
    if decision.should_save and decision.proxy_url:
        proxy_pref.save_preference(
            decision.proxy_url, home=proxy_pref.home_from_env(env),
        )
    return result
