"""平台识别、认证指引和依赖检查。

核心 Git 逻辑跨平台，但系统代理检测目前只有 Windows 实现，
认证指引也按平台给出可执行的终端步骤，避免给 Mac/Linux 用户发 PowerShell。
"""
import subprocess
import sys


WINDOWS_GUIDANCE = (
    "GitHub 凭据未配置、已失效或当前账号无权访问远程。请打开 Windows PowerShell"
    "（Win+R 输入 powershell），不要在 Codex 对话框发送命令，也无需进入项目目录。"
    "先执行 gh auth login，按提示选择 GitHub.com、HTTPS 和浏览器登录；"
    "成功后回到同一个 PowerShell 窗口执行 gh auth setup-git，再用 gh auth status 检查；"
    "使用 SSH 时改为配置本机 SSH 密钥并用 ssh -T git@github.com 验证。"
    "不要把密码或 Token 发给 Codex。配置后重新运行本任务。"
)

GENERIC_GUIDANCE = (
    "GitHub 凭据未配置、已失效或当前账号无权访问远程。请打开系统终端"
    "（macOS 是“终端”应用，Linux 是你的终端模拟器），先确认已安装 GitHub CLI，"
    "再执行 gh auth login，按提示选择 GitHub.com、HTTPS 和浏览器登录；"
    "成功后执行 gh auth setup-git，再用 gh auth status 检查。"
    "不使用 gh 时，配置本机 SSH 密钥并用 ssh -T git@github.com 验证。"
    "不要把密码或 Token 发给 Codex。配置后重新运行本任务。"
    "注意：系统代理残留检测当前仅支持 Windows，其他系统请先手动检查代理设置。"
)


def is_windows(platform_name=None):
    platform_name = sys.platform if platform_name is None else platform_name
    return platform_name == "win32"


def auth_guidance(platform_name=None):
    platform_name = sys.platform if platform_name is None else platform_name
    if platform_name == "win32":
        return WINDOWS_GUIDANCE
    return GENERIC_GUIDANCE


def default_git_runner(command):
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8",
    )
    return result.returncode


def git_available(runner=None):
    """git 不在 PATH 或返回非零都算不可用，异常不外抛。"""
    runner = runner or default_git_runner
    try:
        return runner(["git", "--version"]) == 0
    except OSError:
        return False


def check_dependencies(platform_name=None, git_runner=None):
    """启动时的前置依赖检查，全部满足返回 None。"""
    if not git_available(runner=git_runner):
        return {
            "status": "missing_dependency",
            "error": "未在 PATH 中找到可用的 git，请先安装 Git 并确认 git --version 能正常输出",
        }
    return None
