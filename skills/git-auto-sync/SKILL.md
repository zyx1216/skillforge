---
name: git-auto-sync
description: 在 Codex 完成项目修改并验证后，根据实际改动生成中文提交说明，提交指定文件并推送到当前分支的 upstream。用户要求启用自动 Git 提交、同步或推送时使用；不用于文件保存监听、后台定时同步、强制推送或自动解决冲突。
---

# Git 自动同步

用户明确启用后，在每次任务完成时同步代码。此 skill 只在 Codex 会话内运行，不会监听文件，也不会在 Codex 未运行时推送。

## 前置条件

核心提交与推送逻辑跨平台，Windows、macOS、Linux 均支持，系统代理残留检测也已覆盖三个平台：Windows 读注册表，macOS 用 `networksetup`，Linux 第一版只支持 GNOME 的 `gsettings`，KDE 和无桌面环境会跳过这项检测。认证失败时执行器按平台给终端指引，Windows 给 PowerShell 步骤，macOS/Linux 给通用终端步骤。

本机必须已安装 Git 且 `git --version` 能正常输出，并装有 Python 3。执行器在任何 Git 操作前先做依赖检查，找不到可用的 git 时直接返回 `missing_dependency`（退出码 8），不产生提交。

本机必须已有 GitHub 推送凭据，skill 只复用本机凭据，不得索要密码或 Token。需要提醒用户配置凭据，或排查认证、代理失败时，先读 [references/setup.md](references/setup.md)，按里面的 PowerShell 步骤回复，不要自创配置流程。

首次上传且还没有远程仓库时，必须分别向用户确认 **GitHub 仓库名**和**可见性（公开/私有）**，两项都明确后才能创建。推荐英文小写短横线命名，并优先建议私有；不得默认公开，不得仅根据本地目录名擅自决定。已有远程时不得擅自改名或改变可见性。

## 执行流程

1. 修改前运行 `git status`。已有任何暂存内容，或本任务将修改的文件已有未提交改动时，停止自动同步并让用户先拆分或提交；不要保存、清空或重写用户索引。
2. 修改后运行 `git status --short` 和 `git diff -- <本任务路径>`。没有实际改动则结束，不创建空提交。
3. 检查待提交路径和 diff，不读取或输出凭据内容。执行器会拦两类风险：敏感文件名，以及暂存 diff 新增行里疑似写死的密钥（`password`、`token`、`api_key` 等被赋了非占位符的值）。命中任一情况都停止并让用户判断；`.env.example` 这类模板和 `<your-token>`、`${VAR}` 占位符会放行。内容扫描不是完整密钥审计，公开前仍要人工过一遍 diff。
4. 运行项目已有的测试、构建或可行的最小验证。验证失败则保留改动，不提交、不推送。
5. 根据实际 diff 生成简体中文提交说明，写清改了什么、为什么。不得使用 `update`、`auto commit` 等固定模板。
6. 保持当前工作目录在目标仓库，使用本 skill 的绝对路径调用执行器，只传入本任务相关路径：

   ```bash
   python "<skill目录>/scripts/sync.py" --message "<中文提交说明>" --allow-dirty -- <路径1> <路径2>
   ```

   Windows 可将 `python` 换为用户已有的 Python 3 路径。`--allow-dirty` 表示你已确认这些路径中的改动均由本任务产生，只跳过脏路径复查，不会绕过全仓库预暂存检查。执行器使用 30 秒 Git 命令超时，正常返回结构化状态，不输出凭据。

7. 根据 JSON 结果处理：
   - `pushed`：本地提交和 upstream 推送均成功。
   - `no_changes`：没有需要提交的改动。
   - `missing_upstream`：本地提交已保留。已有 GitHub 空仓库时提示关联地址；需要新建仓库时，先确认仓库名和公开/私有，未经两项确认不得创建。
   - `authentication_required`：预检发现未登录、凭据失效或账号无权限，向用户展示 `setup` 中的配置步骤；此状态在提交前返回，不得索要 Token。
   - `remote_unavailable`：远程地址不存在、网络不可用或无法确认权限，展示脱敏错误并让用户检查地址与网络。
   - `proxy_error`：代理未启动或端口错误。执行器只探测本机回环的常见代理端口，`setup` 会给出当前在监听的替代端口和一次性命令；没有可用端口时才建议直连绕过。不得自动修改代理或自动绕过，只有用户明确同意时才建议手动执行命令。
   - `network_choice_required`：连接状态机启用后直连重试三次全败，需要用户决定继续直连还是提供代理。展示诊断里的重试次数、443/22 端口状态、已记住代理是否存活、系统代理是否残留，按 [references/setup.md](references/setup.md) 的“收到 network_choice_required 后怎么回答”用命令行参数重跑，不自动改网络。继续直连在原命令加 `--retry-direct`；提供代理加 `--proxy <url>`，要同时记住再加 `--remember-proxy`。两个选择互斥，`--remember-proxy` 必须配合 `--proxy`，参数组合不合法会返回 `invalid_arguments`。
   - `direct_unavailable`：用户选了继续直连，第二轮三次仍全败。明确告知当前窗口直连 GitHub 不可用，不再重试，等用户切换网络或提供代理。
   - 决策结果带 `remote_risk=true` 时，说明代理不是本机回环地址，要先提示凭据泄露风险再让用户确认。
   - `blocked_sensitive_path`：敏感文件未提交，告知用户具体路径。
   - `push_failed`：本地提交已保留，报告 Git 错误；不要强推，不要自动 merge 或 rebase。
   - `preexisting_staged_changes` / `preexisting_dirty_paths`：用户已有改动需要人工拆分，不要绕过检查。
   - `git_error`：报告失败命令的错误摘要，不声称已经同步。
   - `invalid_arguments`：补齐提交说明和仓库内相对路径后重试。
   - `missing_dependency`：PATH 中找不到可用的 git，提示用户先安装 Git 并用 `git --version` 确认；此状态在任何 Git 操作前返回，不产生提交。

## 安全边界

- 已有 upstream 时只推送当前分支的 upstream。没有 upstream 时，仅在远程列表唯一为 `origin`、当前为具名分支且 `origin` 可访问时，执行 `git push -u origin <当前分支>`；其他情况保留本地提交并停止。
- 禁止 `--force`、`--force-with-lease` 和其他改写远程历史的操作。
- 认证失败不自动重试，避免反复试错；网络连接由下一条状态机做有限重试，最终仍失败时停下，由用户判断后重新执行。
- 连接状态机默认启用：直连最多重试 3 次、单次超时约 6 秒、间隔 1 到 2 秒；三败才停下询问，选继续直连再做一轮即止，不无限重试。确实需要旧行为时，用环境变量 `GIT_SYNC_NETWORK_STATE=0` 显式关闭，不设或设其他值都保持启用。
- 代理只通过一次性 `git -c http.proxy=...` 注入，不改全局 gitconfig。用户选“记住”才写入 `~/.git-auto-sync/proxy.json`，该文件在仓库外、不进版本库，删除即清除。远程代理地址标记风险，本机回环地址才视为安全。
- 使用代理前先验证可用性：HTTP 代理要能对 `github.com:443` 建立 CONNECT 隧道，SOCKS5 代理要能完成无认证握手；端口活着但隧道或握手失败时回到 `network_choice_required`，`reasons` 带 `proxy_node_failed`，不带坏代理继续推送。
- 显式 `--proxy`（或兼容的 `GIT_SYNC_PROXY`）代表用户已指定走代理，执行器跳过首轮直连、直接校验并使用该代理，避免“TCP 通但 TLS 被重置”的直连误判；已“记住”的代理属于自动兜底，仍按先直连、三败后才启用的顺序走。
- 系统代理只检测不自动复位：识别出残留或节点问题后提示用户，复位操作由用户自己完成。
- 沙箱或命令审批要求用户批准时，正常请求批准，不尝试绕过。
- 首次创建仓库前分别确认名称与可见性，默认建议私有；已有仓库的公开/私有状态不自动修改。
- 保护分支或需要 Pull Request 的仓库不启用直接推送，改为提交后提示用户走 PR。
- 路径检查只能减少误提交，不能代替完整密钥扫描。
- 内容级扫描只检查暂存 diff 的新增行，不检查历史提交，也识别不了经过编码或拆分拼接的密钥。
- Git 命令超时默认 30 秒，可用环境变量 `GIT_SYNC_TIMEOUT` 覆盖；非法或非正数自动回退默认值。
- 执行器不会保存或恢复用户暂存区；存在预暂存内容时直接停止，避免误提交或破坏索引。

## 汇报

分别报告本地提交哈希和推送状态。新建远程时同时报告完整仓库地址和公开/私有状态。没有 upstream 或推送失败时，明确说“本地已提交，GitHub 未更新”，不得把 commit 当成 push 成功。

## 配套文件

- 凭据配置、代理排查、状态码全表：[references/setup.md](references/setup.md)
- 执行器脚本：`scripts/sync.py`
- 测试：`tests/test_sync.py`，在仓库根目录运行 `python -m unittest discover -s skills/git-auto-sync/tests -v`
