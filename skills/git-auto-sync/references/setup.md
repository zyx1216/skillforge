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

### 为什么设了 http_proxy 环境变量还是不生效

Git 自己的 `http.proxy` 配置优先级高于 `http_proxy`、`https_proxy` 这类环境变量。如果全局 Git 配置写的是旧端口，只在 PowerShell 里 `$env:http_proxy=...` 会被 Git 忽略。另外 Git 不读 `all_proxy`，所以给 `all_proxy` 设 socks5 地址对 Git 推送没有作用。

### 执行器会给出的提示

代理失败时，执行器只探测本机回环地址的常见代理端口（7890、7897、10808、10809、20890、20891、8080、1080），不做外网扫描。如果发现有端口在监听，`setup` 会直接给出指向该端口的一次性命令，例如：

```powershell
git -c http.proxy=http://127.0.0.1:20891 -c https.proxy=http://127.0.0.1:20891 push
```

没有探测到可用端口，且你确认当前网络能直连 GitHub 时，再用下面的命令仅本次绕过代理：

如果你确认当前网络能直连 GitHub，可在项目目录的 PowerShell 中仅本次绕过代理：

```powershell
git -c http.proxy= -c https.proxy= push
```

这不会修改全局代理配置。skill 不会自动绕过或修改代理；其他网络问题会返回 `remote_unavailable`。

### HTTP 代理端口在监听但 TLS 中断

代理软件在运行、端口也在监听，Git 仍报 `TLS connect error ... unexpected eof while reading` 时，说明这个 HTTP 代理端口对 GitHub 的 HTTPS 隧道有问题，换同一软件的 SOCKS5 端口通常能通。2026-11-10 在本机实测：HTTP 端口 20891 连续两次 TLS 中断，改用 SOCKS5 端口 7894 后一次成功。

```powershell
git -c http.proxy=socks5h://127.0.0.1:7894 -c https.proxy=socks5h://127.0.0.1:7894 push
```

用 `socks5h` 而不是 `socks5`，域名解析也交给代理处理。先跑 `netstat -ano | findstr LISTENING` 确认本机实际在监听的端口，再替换命令里的端口号。这同样只是一次性参数，不改全局配置。

### 让配置长期生效

如果代理软件的固定端口和全局 Git 配置不一致，可以让用户自己决定是否更新全局配置。查看当前配置用 `git config --get http.proxy`，修改用 `git config --global http.proxy http://127.0.0.1:<端口>`。执行器不替用户改全局配置。

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
| `blocked_sensitive_path`（带 `findings`） | 暂存 diff 的新增行疑似写死密钥，已回滚暂存且未提交 |
| `push_failed` | 本地提交已保留，推送失败，例如远程分叉 |
| `git_error` | Git 命令本身执行失败 |
| `invalid_arguments` | 调用参数不对，例如没给路径或提交说明 |
| `preexisting_staged_changes` | 暂存区已有用户自己的改动，需人工拆分 |
| `preexisting_dirty_paths` | 任务文件在动手前就有未提交改动，需人工确认 |

## 限制

- 敏感文件名检查加新增行内容扫描都不是完整密钥审计，识别不了编码、拆分或拼接的密钥，公开前仍要人工过一遍 diff。
- 保护分支或需要 PR 审查的仓库不应直接自动推送。
- 网络、认证和远程分叉需要用户处理，执行器不会强推。
- 它不是文件监听器，Codex 未运行时不会同步，手动保存文件不会触发提交。
- Git 命令超时默认 30 秒，大仓库可用 `GIT_SYNC_TIMEOUT` 环境变量调大，值必须是正整数，否则回退默认。

## 测试

测试文件在 `skills/git-auto-sync/tests/`，在仓库根目录运行：

```powershell
$env:PYTHONUTF8='1'; D:\Anaconda\python.exe -m unittest discover -s skills/git-auto-sync/tests -v
```

测试在临时目录创建真实 Git 仓库与 bare 远程，覆盖首次 upstream、后续推送、无改动、敏感路径、无 upstream、远程分叉和代理失败，不访问真实 GitHub。
