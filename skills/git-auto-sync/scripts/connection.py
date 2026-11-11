"""国内网络连接状态机。

决策顺序：先直连重试，成功即直连；三败后按用户已给代理、已记住代理、
系统代理诊断依次处理；需要用户拍板时停下返回 NEED_CHOICE，不自动改网络。
所有网络与状态依赖通过 ConnectionPolicy 注入，测试不碰真实机器。
"""
from urllib.parse import urlparse

import random
import time

from network import (
    DIRECT_ATTEMPTS,
    RETRY_DELAY_MAX,
    RETRY_DELAY_MIN,
    proxy_tunnel,
)
import proxy_pref


DIRECT = "direct"
USE_PROVIDED_PROXY = "use_provided_proxy"
USE_SAVED_PROXY = "use_saved_proxy"
NEED_CHOICE = "need_choice"
DIRECT_UNAVAILABLE = "direct_unavailable"


class DirectPorts:
    """一轮直连探测的 443 和 22 端口状态。"""

    def __init__(self, port_443, port_22):
        self.port_443 = port_443
        self.port_22 = port_22


class SystemProxyInfo:
    def __init__(self, host, port, listening, residual):
        self.host = host
        self.port = port
        self.listening = listening
        self.residual = residual


class ConnectionPolicy:
    def __init__(
        self, direct_probe, proxy_port_probe=None, saved_proxy=None,
        system_proxy=None, remember=False, provided_proxy=None,
        retry_direct=False, sleep=None, attempts=DIRECT_ATTEMPTS,
        git_proxy=None, env_proxy=None,
        proxy_tunnel_probe=None,
    ):
        self.direct_probe = direct_probe
        self.proxy_port_probe = proxy_port_probe or (lambda url: True)
        self.saved_proxy = saved_proxy
        self.system_proxy = system_proxy
        self.remember = remember
        self.provided_proxy = (provided_proxy or "").strip() or None
        self.retry_direct = retry_direct
        self.sleep = sleep if sleep is not None else time.sleep
        self.attempts = attempts
        self.direct_attempts = 0
        self.last_direct_ports = DirectPorts(False, False)
        self.git_proxy = git_proxy
        self.env_proxy = env_proxy
        self.proxy_tunnel_probe = proxy_tunnel_probe or proxy_tunnel

    def run_direct_round(self):
        """一轮直连重试，最多 attempts 次，任一成功即 True。"""
        for index in range(self.attempts):
            self.direct_attempts += 1
            result = self.direct_probe()
            if isinstance(result, DirectPorts):
                self.last_direct_ports = result
                reachable = result.port_443
            else:
                reachable = bool(result)
                self.last_direct_ports = DirectPorts(reachable, reachable)
            if reachable:
                return True
            if index < self.attempts - 1:
                delay = random.uniform(RETRY_DELAY_MIN, RETRY_DELAY_MAX)
                if self.sleep is not None:
                    self.sleep(delay)
        return False

    def proxy_alive(self, proxy_url):
        try:
            host = urlparse(proxy_url).hostname
            port = urlparse(proxy_url).port
        except ValueError:
            return False
        if not host or not port:
            return False
        return bool(self.proxy_port_probe(f"{host}:{port}"))

    def proxy_usable(self, proxy_url):
        """端口存活后再验证代理是否真能建到 GitHub 的隧道。

        HTTP 代理必须 CONNECT 成功，SOCKS5 必须握手成功，失败都回到询问。
        """
        if not self.proxy_alive(proxy_url):
            return False, "saved_proxy_unreachable"
        if self.proxy_tunnel_probe(proxy_url):
            return True, None
        return False, "proxy_node_failed"


class ConnectionDecision:
    def __init__(self, outcome, proxy_url=None, should_save=False,
                 remote_risk=False,
                 diagnostics=None, reasons=None):
        self.outcome = outcome
        self.proxy_url = proxy_url
        self.should_save = should_save
        self.remote_risk = remote_risk
        self.diagnostics = diagnostics or {}
        self.reasons = reasons or []


def _proxy_remote_risk(proxy_url):
    if not proxy_url:
        return False
    return not proxy_pref.is_loopback(proxy_url)


def build_diagnostics(policy):
    diagnostics = {
        "direct_attempts": policy.direct_attempts,
        "direct_ports": {
            "port_443": policy.last_direct_ports.port_443,
            "port_22": policy.last_direct_ports.port_22,
        },
    }
    if policy.git_proxy:
        diagnostics["git_proxy"] = policy.git_proxy
    if policy.env_proxy:
        diagnostics["env_proxy"] = policy.env_proxy
    if policy.saved_proxy:
        diagnostics["saved_proxy"] = policy.saved_proxy
        diagnostics["saved_proxy_alive"] = policy.proxy_alive(policy.saved_proxy)
    if policy.system_proxy:
        diagnostics["system_proxy"] = {
            "host": policy.system_proxy.host,
            "port": policy.system_proxy.port,
            "listening": policy.system_proxy.listening,
            "residual": policy.system_proxy.residual,
        }
    return diagnostics


def plan_connection(policy):
    if policy.run_direct_round():
        return ConnectionDecision(DIRECT)

    if policy.retry_direct:
        if policy.run_direct_round():
            return ConnectionDecision(DIRECT)
        return ConnectionDecision(
            DIRECT_UNAVAILABLE,
            diagnostics=build_diagnostics(policy),
            reasons=_direct_failure_reasons(policy, ["second_round_failed"]),
        )

    if policy.provided_proxy:
        usable, reason = policy.proxy_usable(policy.provided_proxy)
        if usable:
            return ConnectionDecision(
                USE_PROVIDED_PROXY,
                proxy_url=policy.provided_proxy,
                should_save=policy.remember,
                remote_risk=_proxy_remote_risk(policy.provided_proxy),
            )
        return ConnectionDecision(
            NEED_CHOICE,
            diagnostics=build_diagnostics(policy),
            reasons=["direct_round_failed", reason],
        )

    reasons = _direct_failure_reasons(policy, ["direct_round_failed"])
    if policy.saved_proxy:
        usable, reason = policy.proxy_usable(policy.saved_proxy)
        if usable:
            return ConnectionDecision(
                USE_SAVED_PROXY,
                proxy_url=policy.saved_proxy,
                remote_risk=_proxy_remote_risk(policy.saved_proxy),
            )
        reasons.append(reason)

    if policy.system_proxy:
        if policy.system_proxy.residual:
            reasons.append("system_proxy_residual")
        else:
            reasons.append("system_proxy_node_issue")

    return ConnectionDecision(
        NEED_CHOICE,
        diagnostics=build_diagnostics(policy),
        reasons=reasons,
    )


def _direct_failure_reasons(policy, reasons):
    ports = policy.last_direct_ports
    if not ports.port_443 and ports.port_22:
        reasons.append("ssh_available")
    return reasons
