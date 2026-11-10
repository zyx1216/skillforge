"""网络探测与系统代理检测。

所有真实 socket、注册表读取都通过函数参数注入，测试可完全 mock，
不依赖运行机器是否联网或是否开着代理。
"""
import random
import re
import socket


GITHUB_HOST = "github.com"
DIRECT_ATTEMPTS = 3
DIRECT_TIMEOUT = 6
RETRY_DELAY_MIN = 1
RETRY_DELAY_MAX = 2


class RegistryUnavailable(RuntimeError):
    """当前平台没有 Windows 注册表，或注册表读取失败。"""


class SystemProxyStatus:
    def __init__(self, host, port, port_listening, residual):
        self.host = host
        self.port = port
        self.port_listening = port_listening
        self.residual = residual


class DirectCheckResult:
    def __init__(self, port_443, port_22):
        self.port_443 = port_443
        self.port_22 = port_22


def default_socket_probe(host, port, timeout):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, int(port))) == 0


def tcp_reachable(host, port, timeout=DIRECT_TIMEOUT, probe=None, socket_factory=None):
    """阻塞式 TCP 连通性探测，任何异常都归为不可达，不向外抛。"""
    if probe is not None:
        return bool(probe(host, port, timeout))
    if socket_factory is not None:
        try:
            sock = socket_factory(socket.AF_INET, socket.SOCK_STREAM)
            with sock:
                sock.settimeout(timeout)
                return sock.connect_ex((host, int(port))) == 0
        except OSError:
            return False
    try:
        return default_socket_probe(host, port, timeout)
    except OSError:
        return False


def check_github_direct(timeout=DIRECT_TIMEOUT, probe=None):
    """分别探测 443 和 22，返回两个端口各自的可达性。"""
    port_443 = tcp_reachable(GITHUB_HOST, 443, timeout=timeout, probe=probe)
    port_22 = tcp_reachable(GITHUB_HOST, 22, timeout=timeout, probe=probe)
    return DirectCheckResult(port_443, port_22)


def wait_for_direct(attempts=DIRECT_ATTEMPTS, timeout=DIRECT_TIMEOUT, probe=None, sleep=None):
    """直连重试，任一轮 443 可达即成功；全败返回 False。

    间隔在 1 到 2 秒间随机，最后一轮失败后不再 sleep。
    """
    sleep = sleep or __import__("time").sleep
    for index in range(attempts):
        if tcp_reachable(GITHUB_HOST, 443, timeout=timeout, probe=probe):
            return True
        if index < attempts - 1:
            sleep(random.uniform(RETRY_DELAY_MIN, RETRY_DELAY_MAX))
    return False


def read_windows_proxy_registry():
    """读当前用户的 Windows 系统代理开关和地址，非 Windows 抛 RegistryUnavailable。"""
    try:
        import winreg
    except ImportError as error:
        raise RegistryUnavailable("当前平台没有 winreg 模块") from error
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        try:
            enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            try:
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
            except FileNotFoundError:
                server = ""
        finally:
            winreg.CloseKey(key)
    except OSError as error:
        raise RegistryUnavailable(str(error)) from error
    return {"ProxyEnable": int(enable), "ProxyServer": str(server)}


def parse_proxy_server(raw):
    """从系统代理地址里取第一个 host 和端口。

    兼容纯 host:port、带 scheme、以及 http=...;https=... 多协议格式。
    """
    if not raw:
        return None
    first = raw.split(";")[0].strip()
    if "=" in first and ":" in first.split("=", 1)[1]:
        first = first.split("=", 1)[1].strip()
    first = re.sub(r"^[a-z][a-z0-9+.-]*://", "", first, flags=re.IGNORECASE)
    match = re.match(r"^\[?([^\[\]:]+)\]?:(\d+)$", first)
    if not match:
        return None
    host, port = match.group(1), int(match.group(2))
    if not (0 < port < 65536):
        return None
    return host, port


def detect_system_proxy(registry_reader=None, port_probe=None):
    """通用系统代理检测，不绑定任何代理软件品牌。

    开关关闭、非 Windows、地址损坏都返回 None。
    开关打开但端口无服务，判定为残留；端口有服务则是节点或规则问题。
    """
    registry_reader = registry_reader or read_windows_proxy_registry
    port_probe = port_probe or (lambda port: default_socket_probe("127.0.0.1", port, timeout=1))
    try:
        values = registry_reader()
    except RegistryUnavailable:
        return None
    if not values.get("ProxyEnable"):
        return None
    parsed = parse_proxy_server(values.get("ProxyServer", ""))
    if parsed is None:
        return None
    host, port = parsed
    listening = bool(port_probe(port))
    return SystemProxyStatus(host, port, listening, residual=not listening)
