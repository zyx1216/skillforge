# git-auto-sync 配置与排障手册

这份文档只在配置 GitHub 凭据、排查推送失败时阅读。日常使用看 SKILL.md 即可。

## 先确认前置依赖

执行器依赖本机的 Git 和 Python 3，先在终端确认两者都在 PATH 中：

```powershell
git --version
python --version
```

`git --version` 提示找不到命令时，先安装 Git for Windows（macOS 装 Xcode Command Line Tools 或 Git，Linux 用发行版包管理器），重新打开终端再确认。执行器启动时会先做这层检查，找不到可用的 git 直接返回 `missing_dependency`（退出码 8），不会进入任何提交流程。

## 前置配置 GitHub 凭据

不需要把 GitHub 密码或 Token 提供给 Codex，skill 只复用本机已有凭据。

### HTTPS（推荐）

以下命令在系统终端中执行，不是在 Codex 对话框里发送，也不需要先 cd 到项目。

- Windows：按 Win + R，输入 powershell 并回车打开 Windows PowerShell。
- macOS：打开“终端”应用。
- Linux：打开你的终端模拟器。

先确认已安装 GitHub CLI（`gh --version` 有输出），没有则先安装再重新打开终端。然后：

1. 在终端运行 `gh auth login`。
3. 按窗口中的问题依次选择 GitHub.com、HTTPS、浏览器登录。窗口显示一次性验证码后，复制验证码，在自动打开的 GitHub 网页中登录并授权。
4. 回到终端，登录成功后运行 `gh auth setup-git`。这条命令让本机 Git 在推送时复用刚才的 GitHub 登录凭据。
5. 最后运行 `gh auth status`，看到已登录账号即完成。以后 Codex 执行 git push 时会使用这套凭据。

### SSH

SSH 命令同样在系统终端中执行，Windows 用户用 PowerShell，macOS/Linux 用各自的终端。

1. 在本机生成或复用 SSH 密钥，并把公钥添加到 GitHub 账号的 Settings → SSH and GPG keys。
2. 确认仓库远程使用 SSH 地址，例如 `git@github.com:用户名/仓库.git`。
3. 运行 `ssh -T git@github.com` 验证连接。

未配置、凭据失效或账号无权限时，执行器会在提交前返回 `authentication_required` 和配置提醒，不会要求你发送密码或 Token。Windows 用户收到的指引是 PowerShell 步骤，macOS/Linux 用户收到的是通用终端步骤。注意系统代理残留检测目前只有 Windows 实现，其他系统需要你自己手动检查代理设置。

## 为什么浏览器能打开 GitHub，git 却报无法接入

浏览器和 git 对网络抖动的处理方式不一样。浏览器会自动重试、容忍 TLS 抖动和短时连不上，一次请求内部会换连接再试；git 是一次性命令，单次连接失败立刻报错退出。国内直连 GitHub 本身是间歇性可达，同一台机器、不开代理，可能这一分钟 443 端口超时，过几分钟又能连上。所以“浏览器能进、git 报错”通常不是凭据问题，而是 git 没有替你重试。

这个 skill 的连接状态机就是为消化这种抖动设计的，行为固定：

1. 先做直连重试，最多 3 次，单次超时约 6 秒，间隔 1 到 2 秒。
2. 任一次连通就正常提交推送，整个过程不需要你干预。
3. 三次都失败才停下来诊断，返回 `network_choice_required`，由你选继续直连还是提供代理。
4. 选继续直连会再做一轮 3 次，仍失败就返回 `direct_unavailable`，明确告知当前窗口直连不可用，不会无限重试。
5. 你提供代理后本轮用一次性 `git -c http.proxy=...` 注入；选“记住”才写入本地状态文件，以后直连三败时自动兜底。

连接状态机默认启用，不需要任何开关就会自动重试和诊断。只有确实想恢复旧行为、完全不做探测时，才在调用执行器时设置环境变量 `GIT_SYNC_NETWORK_STATE=0` 作为逃生舱；不设这个变量或设成其他值都保持启用。重试次数、超时和间隔都是脚本里的固定常量，不读外部配置。

## 收到 network_choice_required 后怎么回答

执行器返回 `network_choice_required`（退出码 7）时还没有产生提交，改动完整保留在工作区。它不会自己决定走哪条路，需要你在原命令上加上对应参数重新调用执行器。推荐用命令行参数，直观、可复制，也不会污染终端环境。

### 选项 A：再试一轮直连

适合你判断只是临时抖动，或刚切换了网络。在原命令上加 `--retry-direct`，执行器会再做一轮 3 次直连；这一轮仍全败会返回 `direct_unavailable`，不会继续无限重试。

```powershell
python "<skill目录>/scripts/sync.py" --retry-direct --message "<中文提交说明>" --allow-dirty -- <路径>
```

### 选项 B：提供代理

在原命令上加 `--proxy <url>`，执行器会先验证端口存活，再确认代理真能连到 `github.com:443`：HTTP 代理要能建立 CONNECT 隧道，SOCKS5 代理要能完成无认证握手。端口在监听但隧道或握手失败，说明代理节点本身有问题，执行器会返回 `network_choice_required` 并在 `reasons` 里带 `proxy_node_failed`，不会带着坏代理走到推送失败。验证通过才用一次性 `git -c http.proxy=...` 推送。

```powershell
python "<skill目录>/scripts/sync.py" --proxy "http://127.0.0.1:20891" --message "<中文提交说明>" --allow-dirty -- <路径>
```

希望以后直连三败时自动用这个代理兜底，就再加 `--remember-proxy`，地址会写入 `~/.git-auto-sync/proxy.json`。只在这一轮用就不要加这个开关。

```powershell
python "<skill目录>/scripts/sync.py" --proxy "http://127.0.0.1:20891" --remember-proxy --message "<中文提交说明>" --allow-dirty -- <路径>
```

参数规则：

- `--retry-direct` 和 `--proxy` 互斥，继续直连和提供代理只能二选一，同时给会返回 `invalid_arguments`。
- `--remember-proxy` 必须配合 `--proxy`，单独给会返回 `invalid_arguments`。
- 带 `--proxy` 重跑时仍先做首轮直连，直连恢复就优先直连，直连失败才用代理。

### 兼容：旧的环境变量写法

命令行参数出现之前用的三个环境变量仍然支持，旧脚本和旧文档里的调用不会失效。优先级是命令行参数高于环境变量；同时给时以命令行参数为准。

- `--retry-direct` 等价于 `GIT_SYNC_RETRY_DIRECT=1`。
- `--proxy <url>` 等价于 `GIT_SYNC_PROXY=<url>`。
- `--remember-proxy` 等价于 `GIT_SYNC_REMEMBER_PROXY=1`。

新调用统一用命令行参数，环境变量只作为兼容和自动化场景的备用入口。
```

### 风险提示和状态字段

返回结果里的 `remote_risk` 为 `true` 时，说明代理地址不是本机回环（`127.0.0.1`、`localhost`、`::1`），Git 流量会经过别人的服务器，存在凭据泄露风险，应先确认来源可信再继续。诊断字段 `diagnostics` 里还会给出最后一轮 443 和 22 端口状态：443 阻断但 22 通时 `reasons` 带 `ssh_available`，可以考虑把远程切到 SSH；`system_proxy_residual` 表示系统代理残留，按本文的复位方法处理。

## 系统代理残留（任何代理软件都可能出现）

代理软件开“系统代理模式”时，会把 Windows 的系统代理开关打开并指向自己的本地端口。如果软件异常退出、没正常关闭，这个开关可能残留为开，但指向的端口已经没有服务，结果连国内网站也打不开。这不是某一款软件的问题，任何改系统代理的工具异常退出都可能留下这个状态。

skill 会做通用检测，不针对具体品牌：读 Windows 系统代理开关和它指向的端口，再用 socket 测那个端口有没有服务。

- 开关为开、端口无服务：判定为系统代理残留，在 `network_choice_required` 的诊断里给出 `system_proxy_residual`。
- 开关为开、端口有服务但仍连不上：归为代理软件的节点或规则问题，标记 `system_proxy_node_issue`，不叫残留。

skill 只检测和提示，不会自动复位系统代理。确认是残留后，复位由你自己操作，二选一：

1. 重新打开你的代理软件，正常退出一次，让它把系统代理开关关回去。
2. 在 Windows 设置 → 网络和 Internet → 代理 → 手动设置代理，把“使用代理服务器”关掉。

## 记住的代理存在哪里

选“记住代理”后，地址写在用户主目录下的 `~/.git-auto-sync/proxy.json`，这是仓库外的本地文件，不会进开源仓库，也不改全局 gitconfig。删除这个文件就等于清除记忆，执行器下次三败时会重新询问。只接受本机回环地址（`127.0.0.1`、`localhost`、`::1`）作为无风险代理；填远程地址会被标记 `remote_risk`，因为把 Git 流量交给别人的服务器有凭据泄露风险。

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
| `missing_dependency` | PATH 中找不到可用的 git，依赖检查未通过（退出码 8），不产生提交 |
| `no_changes` | 没有需要提交的改动 |
| `missing_upstream` | 本地提交已保留，但当前分支没有 upstream，无法自动推送 |
| `authentication_required` | 提交前预检发现未登录、凭据失效或账号无权限 |
| `proxy_error` | Git 配置了代理但代理连不上 |
| `network_choice_required` | 直连重试三次全败，需要你选继续直连还是提供代理（退出码 7） |
| `direct_unavailable` | 选了继续直连，第二轮仍三次全败，当前窗口直连不可用（退出码 7） |
| `remote_unavailable` | 远程地址不存在、网络不可用或无法确认权限 |
| `blocked_sensitive_path` | 待提交路径里有敏感文件，已拦下未提交 |
| `blocked_sensitive_path`（带 `findings`） | 暂存 diff 的新增行疑似写死密钥，已回滚暂存且未提交 |
| `push_failed` | 本地提交已保留，推送失败，例如远程分叉 |
| `git_error` | Git 命令本身执行失败 |
| `invalid_arguments` | 调用参数不对，例如没给路径或提交说明 |
| `preexisting_staged_changes` | 暂存区已有用户自己的改动，需人工拆分 |
| `preexisting_dirty_paths` | 任务文件在动手前就有未提交改动，需人工确认 |

## 限制

- 当前仅在 Windows 上完整支持。提交、推送、凭据和代理状态机本身跨平台，但系统代理残留检测依赖 Windows 注册表，macOS/Linux 上会自动跳过这一项，认证指引也改为通用终端版本。
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
