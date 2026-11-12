# git-auto-sync 真实环境 E2E 手动清单

自动化测试只在本地临时 Git 仓库和 HTTP 假服务器上运行，不访问真实 GitHub。下面的场景需要人工按需执行，每次发布大版本前至少跑一遍场景 1 和场景 4。

## 终评剩余项的两步走（2026-11）

代码层面的评审问题已全部闭环，唯一剩的是真实环境 E2E，性质是验证缺口而不是缺陷。不用一次全做，按下面两步降低门槛：

1. 先跑场景 8，在当前这台机器、当前网络下把“三败提问到命令行参数回答”这条交互链路真机走通，其中 `--proxy` 路径用已知可用的本地代理，可以确定性地走到 `pushed`。
2. 场景 2、3、5（私有仓库、无权限、保护分支、远程分叉）等方便建测试仓库时再按本清单逐步补，每次跑完把结果回填到文末的真实执行记录。

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

## 场景 8：三败问答的命令行交互（终评第一步，优先跑）

目标是在真机走通“执行器返回 `network_choice_required` 到用命令行参数回答”的完整链路，验证 `--retry-direct`、`--proxy`、`--remember-proxy` 三个参数在真实网络下可用。建议在一个专门的测试仓库里做，避免污染日常项目；不要在生产仓库反复制造推送失败。

前置：本机凭据可用，有一个能推送的真实远程；记下当前已知可用的本地代理端口（本机实测 SOCKS5 为 `socks5h://127.0.0.1:7894`，以当时实际监听为准）。

### 8.1 触发提问并核对诊断

1. 在测试仓库做一个普通文本小改动。
2. 在直连 GitHub 不通的时间窗调用执行器（不带任何网络参数）。直连本身是间歇性的，没触发三败就等网络抖动时重试，不要改代码去强行制造失败。
3. 预期返回退出码 7、状态 `network_choice_required`，且没有产生提交，`git log` 的 HEAD 不变、改动仍在工作区。
4. 核对 JSON 里的 `diagnostics`：`direct_attempts` 为 3，`direct_ports` 同时给出 443 和 22 状态；若系统代理有残留或节点问题，`reasons` 里应出现对应标记。

### 8.2 用 `--retry-direct` 回答

在原命令上加 `--retry-direct` 重跑：

```powershell
python "<skill目录>/scripts/sync.py" --retry-direct --message "<中文提交说明>" --allow-dirty -- <路径>
```

预期两种结果都算符合：直连恢复时返回 `pushed`；这一轮三次仍全败时返回 `direct_unavailable`（退出码 7），且 `direct_attempts` 累计到 6，不会无限重试。

### 8.3 用 `--proxy` 回答（可确定性走通）

在原命令上加 `--proxy`。显式代理会跳过首轮直连，直接做端口存活和协议握手校验，所以不依赖直连何时恢复，能稳定验证参数链路：

```powershell
python "<skill目录>/scripts/sync.py" --proxy "socks5h://127.0.0.1:7894" --message "<中文提交说明>" --allow-dirty -- <路径>
```

预期执行器不跑直连探测，直接做端口存活和 SOCKS5 握手校验，通过后用一次性 `git -c http.proxy=...` 推送，返回 `pushed`；用 `git config --get http.proxy` 复查，确认全局 gitconfig 没被改动。

2026-11-11 真机记录：首次跑 8.3 时旧实现仍先做直连探测，当时 TCP 443 能握手但 TLS 被重置，执行器误判直连可用、忽略了显式 `--proxy`，git 直连被 RST，返回 `remote_unavailable`。据此把语义改为“显式代理跳过直连”，自动化测试补了直连成功和直连失败两组用例；修复后需在本测试场重跑 8.3 回填结果。

2026-11-12 真机记录：上一处修复后重跑，`direct_attempts=0` 证明显式代理已跳过直连，但又暴露出第二个被 mock 掩盖的 bug。`connection.proxy_alive` 原本把完整代理 URL 降级成无 scheme 的 `host:port` 字符串再传给端口探针，而真实探针用 `urlparse` 解析它，无 scheme 时 `hostname/port` 都是 `None`，导致真实环境端口探测恒为失败、返回 `network_choice_required` 且 `reasons` 带 `saved_proxy_unreachable`（此时代理端口和 SOCKS5 握手实测都正常）。单测因为把探针 mock 成固定值从未触发解析。修复为把完整代理 URL 直接传给探针，并新增一个用本地真实 TCP 端口、不 mock 探针的集成测试锁定。

2026-11-12 重跑结果（通过）：在私有测试仓库 `skill-testing-lab` 用执行器带 `--proxy socks5h://127.0.0.1:7894` 跑通，返回 `pushed`，新提交 `c653f9f` 只含目标文件，提交说明由执行器写入，本地 `HEAD` 与 `origin/main` 一致、upstream 为 `origin/main`，工作区干净，全局 `http.proxy` 仍为空，确认一次性 `-c` 注入没有改全局配置。至此“显式代理参数回答 → 执行器校验 → 提交 → 推送”这条命令行交互链路真机闭环，8.3 标记通过。

### 8.4 验证记住代理和参数冲突

1. 再加 `--remember-proxy` 重跑一次，预期 `~/.git-auto-sync/proxy.json` 写入该地址，之后直连三败时能自动兜底。
2. 单独给 `--remember-proxy`（不带 `--proxy`），预期返回 `invalid_arguments`，不产生提交。
3. 同时给 `--retry-direct` 和 `--proxy`，预期同样返回 `invalid_arguments`。
4. 验证完删除 `~/.git-auto-sync/proxy.json`，清除这次测试写入的记忆。

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
