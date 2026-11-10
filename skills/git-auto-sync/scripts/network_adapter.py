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
        return lambda: True
    if mode == "fail":
        return lambda: False
    return None


def _test_system_proxy(env):
    mode = env.get("GIT_SYNC_TEST_SYSTEM_PROXY")
    if mode == "residual":
        return connection.SystemProxyInfo("127.0.0.1", 7890, False, True)
    if mode == "node":
        return connection.SystemProxyInfo("127.0.0.1", 7890, True, False)
    return None


def build_policy(env):
    test_probe = _test_direct_probe(env)
    if test_probe is not None:
        direct_probe = test_probe
    else:
        def direct_probe():
            return network.tcp_reachable(network.GITHUB_HOST, 443, timeout=network.DIRECT_TIMEOUT)

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
        sleep=lambda _: None,
    )


def decide_network_action(env):
    if env.get("GIT_SYNC_NETWORK_STATE") != "1":
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
