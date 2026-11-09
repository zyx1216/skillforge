# git-auto-sync 配置与排障手册

这份文档只在配置 GitHub 凭据、排查推送失败时阅读。日常使用看 SKILL.md 即可。

## 前置配置 GitHub 凭据

不需要把 GitHub 密码或 Token 提供给 Codex，skill 只复用本机已有凭据。

### HTTPS（推荐）

以下命令都在 Windows PowerShell 中执行，不是在 Codex 对话框里发送。按 Win + R，输入 powershell 并回车即可打开。命令和当前目录无关，不需要先 cd 到项目。

1. 在 PowerShell 运行 `gh --version`。如果提示找不到 gh，先安装 GitHub CLI，再重新打开 PowerShell。
2. 在同一个 PowerShell 窗口运行 `gh auth login`。
3. 按窗口中的问题依次选择 GitHub.com、HTTPS、浏览器登录。窗口显示一次性验证码后，复制验证码，在自动打开的 GitHub 网页中登录并授权。
4. 回到 PowerShell，登录成功后运行 `gh auth setup-git`。这条命令让本机 Git 在推送时复用刚才的 GitHub 登录凭据。
5. 最后运行 `gh auth status`，看到已登录账号即完成。以后 Codex 执行 git push 时会使用这套凭据。

### SSH

SSH 命令同样在 Windows PowerShell 中执行。

1. 在本机生成或复用 SSH 密钥，并把公钥添加到 GitHub 账号的 Settings → SSH and GPG keys。
2. 确认仓库远程使用 SSH 地址，例如 `git@github.com:用户名/仓库.git`。
3. 运行 `ssh -T git@github.com` 验证连接。

未配置、凭据失效或账号无权限时，执行器会在提交前返回 `authentication_required` 和配置提醒，不会要求你发送密码或 Token。Codex 会明确提醒你在 Windows PowerShell 中完成上述步骤。

## 代理连接失败

如果出现 `proxy_error`，说明 Git 配置了代理但无法连接。Codex 会显示当前代理地址，先检查代理软件是否启动、端口是否一致。

如果你确认当前网络能直连 GitHub，可在项目目录的 PowerShell 中仅本次绕过代理：

```powershell
git -c http.proxy= -c https.proxy= push
```

这不会修改全局代理配置。skill 不会自动绕过或修改代理；其他网络问题会返回 `remote_unavailable`。

## 执行器返回状态一览

| 状态 | 含义 |
| --- | --- |
| `pushed` | 本地提交和 upstream 推送都成功 |
| `no_changes` | 没有需要提交的改动 |
| `missing_upstream` | 本地提交已保留，但当前分支没有 upstream，无法自动推送 |
| `authentication_required` | 提交前预检发现未登录、凭据失效或账号无权限 |
| `proxy_error` | Git 配置了代理但代理连不上 |
| `remote_unavailable` | 远程地址不存在、网络不可用或无法确认权限 |
| `blocked_sensitive_path` | 待提交路径里有敏感文件，已拦下未提交 |
| `push_failed` | 本地提交已保留，推送失败，例如远程分叉 |
| `git_error` | Git 命令本身执行失败 |
| `invalid_arguments` | 调用参数不对，例如没给路径或提交说明 |
| `preexisting_staged_changes` | 暂存区已有用户自己的改动，需人工拆分 |
| `preexisting_dirty_paths` | 任务文件在动手前就有未提交改动，需人工确认 |

## 限制

- 敏感文件名检查不是完整的密钥扫描，公开前仍要人工过一遍 diff。
- 保护分支或需要 PR 审查的仓库不应直接自动推送。
- 网络、认证和远程分叉需要用户处理，执行器不会强推。
- 它不是文件监听器，Codex 未运行时不会同步，手动保存文件不会触发提交。

## 测试

测试文件在 `skills/git-auto-sync/tests/`，在仓库根目录运行：

```powershell
$env:PYTHONUTF8='1'; D:\Anaconda\python.exe -m unittest discover -s skills/git-auto-sync/tests -v
```

测试在临时目录创建真实 Git 仓库与 bare 远程，覆盖首次 upstream、后续推送、无改动、敏感路径、无 upstream、远程分叉和代理失败，不访问真实 GitHub。
