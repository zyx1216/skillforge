"""代理偏好的本地持久化。

状态文件放在用户主目录的隐藏目录，不进任何 Git 仓库，不改全局 gitconfig。
所有路径通过 home 参数注入，测试用临时目录隔离，不碰真实用户目录。
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


STATE_DIR = ".git-auto-sync"
STATE_FILE = "proxy.json"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


class ProxyPreference:
    def __init__(self, proxy_url, remote_risk, saved_at=None):
        self.proxy_url = proxy_url
        self.remote_risk = remote_risk
        self.saved_at = saved_at


def state_path(home):
    return Path(home) / STATE_DIR / STATE_FILE


def is_loopback(proxy_url):
    """只把本机回环地址视为安全，任何其他 host 都算远程代理。"""
    host = (urlparse(proxy_url).hostname or "").lower()
    return host in LOOPBACK_HOSTS


def save_preference(proxy_url, home=None):
    home = Path(home) if home is not None else Path.home()
    proxy_url = (proxy_url or "").strip()
    preference = ProxyPreference(
        proxy_url=proxy_url,
        remote_risk=not is_loopback(proxy_url),
        saved_at=datetime.now(timezone.utc).isoformat(),
    )
    path = state_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "proxy_url": preference.proxy_url,
        "remote_risk": preference.remote_risk,
        "saved_at": preference.saved_at,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return preference


def load_preference(home=None):
    home = Path(home) if home is not None else Path.home()
    path = state_path(home)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    proxy_url = str(data.get("proxy_url", "")).strip()
    if not proxy_url:
        return None
    return ProxyPreference(
        proxy_url=proxy_url,
        remote_risk=bool(data.get("remote_risk", not is_loopback(proxy_url))),
        saved_at=data.get("saved_at"),
    )


def clear_preference(home=None):
    home = Path(home) if home is not None else Path.home()
    path = state_path(home)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    try:
        path.parent.rmdir()
    except (OSError, FileNotFoundError):
        pass


def home_from_env(env=None):
    """测试通过 GIT_SYNC_STATE_HOME 指定隔离目录，线上默认用户主目录。"""
    env = env if env is not None else os.environ
    override = (env.get("GIT_SYNC_STATE_HOME") or "").strip()
    return Path(override) if override else Path.home()
