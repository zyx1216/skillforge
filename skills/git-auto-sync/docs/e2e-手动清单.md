# git-auto-sync 真实环境 E2E 手动清单

自动化测试只在本地临时 Git 仓库和 HTTP 假服务器上运行，不访问真实 GitHub。下面的场景需要人工按需执行，每次发布大版本前至少跑一遍场景 1 和场景 4。

## 场景 1：公开仓库正常推送

前置：本机已通过 `gh auth status` 或 SSH 验证，目标仓库存在且当前分支可直接推送。

1. 在真实仓库做一个小改动，只涉及普通文本文件。
2. 调用执行器，传入该文件路径和中文提交说明。
3. 预期返回 `pushed`，输出里有本地 commit 哈希和 upstream。
4. 在 GitHub 网页刷新，确认提交内容、提交说明和本地一致。

### 核对记录

2026-11-10：第二轮优化的 8 个提交由用户手动 `git push` 推送到公开仓库 `zyx1216/skillforge`，随后用 `git ls-remote origin HEAD refs/heads/main` 核对，远程 `HEAD` 与 `refs/heads/main` 均为 `ffc6e90`，与本地 `HEAD` 一致，公开仓库链路可用。

这次核对覆盖了“本地提交成功到达公开远程”这一段；还没覆盖“由 `sync.py` 执行器直接驱动真实 GitHub 推送并返回 `pushed` 状态”，执行器完整链路仍需在下次任务中实际调用一次后回填。

核对时还发现：本机 HTTP 代理 `127.0.0.1:20891` 对 GitHub HTTPS 连续两次返回 TLS 中断，改用 `socks5h://127.0.0.1:7894` 后一次成功。这条属于环境问题，不是执行器逻辑问题，已同步记入 `MEMORY.md`。

## 场景 2：私有仓库与无权限账号

1. 新建一个私有测试仓库，或让另一个无权限账号作为当前 Git 凭据。
2. 做改动后调用执行器。
3. 预期在提交前返回 `authentication_required`，状态码 6，并带 `setup` 配置指引。
4. 确认 `git log` 没有产生新提交，工作区改动仍保留。

## 场景 3：保护分支

1. 在 GitHub 仓库设置里对 main 启用分支保护，禁止直接推送。
2. 做改动后调用执行器。
3. 预期本地提交保留，推送返回失败类状态，不能强推，也不能自动改保护规则。
4. 记录真实报错被归到 `push_failed`、`authentication_required` 还是其他状态，用于后续校准分类正则。

## 场景 4：代理断开和端口漂移

1. 先正常推送一次，确认凭据和远程没问题。
2. 关闭代理软件，或把 Git `http.proxy` 指向一个没有监听的端口，再调用执行器。
3. 预期返回 `proxy_error`，`setup` 里说明当前代理地址。
4. 启动代理但换成另一个本地端口，确认 `setup` 能探测到正在监听的替代端口，并给出对应的一次性 `git -c http.proxy=...` 命令。
5. 确认执行器没有修改全局 Git 配置，用 `git config --get http.proxy` 复查。

## 场景 5：远程分叉

1. 在另一台机器或另一个克隆里向同一分支推一个新提交。
2. 本地不 pull，直接做改动后调用执行器。
3. 预期本地提交保留、推送失败，返回失败类状态，执行器没有自动 merge、rebase 或强推。

## 场景 6：普通文件里的密钥

1. 在一个普通命名的 `.py` 或 `.yaml` 文件新增一行，例如 `API_KEY = "ghp_真实形态的测试值"`。
2. 调用执行器并传入该文件。
3. 预期返回 `blocked_sensitive_path`，带 `findings` 字段，状态码 3。
4. 确认暂存区已回滚、没有产生提交。
5. 把值改成 `<your-api-key>` 或 `${API_KEY}` 后重跑，预期能正常通过。

## 场景 7：空格和中文文件名

1. 新建名为 `测试 文件.txt` 或 `my file.txt` 的文件并做改动。
2. 不传 `--allow-dirty` 调用执行器，预期 `preexisting_dirty_paths` 的路径不带引号、不乱码。
3. 加 `--allow-dirty` 后重跑，预期正常提交并推送。

## 结果记录

每次执行记录日期、场景、实际状态码和是否符合预期。不符合预期时，先保存脱敏后的命令输出，再决定是补自动化测试还是调整分类规则，不要直接在真实仓库反复试错。

## 真实执行记录（2026-11-10）

在用户真实 Windows 机器上运行，不设 `GIT_SYNC_TEST_*` 变量，使用真实 socket、真实注册表读取。

### 真实环境探针

- 真实注册表读取成功：当前 `ProxyEnable=1`，`ProxyServer` 为多协议格式 `http=127.0.0.1:20891;https=...;socks=...`。
- 真实 socket 直连 github.com：443 可达=true、22 可达=true。
- 真实状态机 `decide_network_action`：直连第一轮成功，`outcome=direct`。
- `parse_proxy_server` 正确解析多协议格式为 `('127.0.0.1', 20891)`。
- 真实 `detect_system_proxy`：20891 在监听，`listening=true、residual=false`，正确判为节点正常而非残留。

### 失败分支（真实 socket 确定性触发）

| 验证点 | 实际结果 | 预期 | 是否符合 |
|---|---|---|---|
| 系统代理残留（指向无服务端口 9） | listening=false, residual=true | residual=true | 是 |
| 节点问题（指向在监听的 20891） | listening=true, residual=false | residual=false | 是 |
| 系统代理关闭 | 返回 None | None | 是 |
| 直连三败 | need_choice，direct_attempts=3 | need_choice | 是 |
| 继续直连第二轮仍败 | direct_unavailable，direct_attempts=6 | direct_unavailable | 是 |
| 三败后已保存代理存活 | use_saved_proxy，proxy=20891 | use_saved_proxy | 是 |
| 真实超时（不可路由 IP，timeout=2） | 精确阻塞 2.0 秒 | 约 2 秒 | 是 |

### 执行器真实推送（场景 1 闭环）

本回填文档由 `sync.py` 执行器直接驱动提交并推送（非手动 `git`），返回 `pushed` 状态及 commit、upstream；以执行器本次 JSON 返回为准。
