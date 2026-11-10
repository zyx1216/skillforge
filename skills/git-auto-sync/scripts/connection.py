"""国内网络连接状态机。

决策顺序：先直连重试，成功即直连；三败后按用户已给代理、已记住代理、
系统代理诊断依次处理；需要用户拍板时停下返回 NEED_CHOICE，不自动改网络。
所有网络与状态依赖通过 ConnectionPolicy 注入，测试不碰真实机器。
"""
from urllib.parse import urlparse

from network import DIRECT_ATTEMPTS


DIRECT = "direct"
USE_PROVIDED_PROXY = "use_provided_proxy"
USE_SAVED_PROXY = "use_saved_proxy"
NEED_CHOICE = "need_choice"
DIRECT_UNAVAILABLE = "direct_unavailable"


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
    ):
        self.direct_probe = direct_probe
        self.proxy_port_probe = proxy_port_probe or (lambda url: True)
        self.saved_proxy = saved_proxy
        self.system_proxy = system_proxy
        self.remember = remember
        self.provided_proxy = (provided_proxy or "").strip() or None
        self.retry_direct = retry_direct
        self.sleep = sleep or (lambda _: None)
        self.attempts = attempts
        self.direct_attempts = 0
        self.git_proxy = git_proxy
        self.env_proxy = env_proxy

    def run_direct_round(self):
        """一轮直连重试，最多 attempts 次，任一成功即 True。"""
        for index in range(self.attempts):
            self.direct_attempts += 1
            if self.direct_probe():
                return True
            if index < self.attempts - 1:
                self.sleep(1)
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


class ConnectionDecision:
    def __init__(self, outcome, proxy_url=None, should_save=False,
                 diagnostics=None, reasons=None):
        self.outcome = outcome
        self.proxy_url = proxy_url
        self.should_save = should_save
        self.diagnostics = diagnostics or {}
        self.reasons = reasons or []


def build_diagnostics(policy):
    diagnostics = {"direct_attempts": policy.direct_attempts}
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
            reasons=["second_round_failed"],
        )

    if policy.provided_proxy:
        return ConnectionDecision(
            USE_PROVIDED_PROXY,
            proxy_url=policy.provided_proxy,
            should_save=policy.remember,
        )

    reasons = ["direct_round_failed"]
    if policy.saved_proxy:
        if policy.proxy_alive(policy.saved_proxy):
            return ConnectionDecision(
                USE_SAVED_PROXY, proxy_url=policy.saved_proxy,
            )
        reasons.append("saved_proxy_unreachable")

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
