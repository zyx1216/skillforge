# Git 自动同步 Skill · MEMORY.md

## 架构决策
- 2026-11-04：采用纯规则 skill，由 Codex 在任务完成后驱动 Git，不开发常驻脚本。
- 2026-11-04：现用 `git-init` 与开源 `git-auto-sync` 分开维护，避免开发过程影响日常使用。
- 2026-11-04：增加可选 Python 标准库执行器，让关键停止条件可测试；Codex 仍负责验证与提交说明。
- 2026-11-09：项目从单 skill 转型为个人 AI 自制 skill 库，全程开源公开（远程已为 PUBLIC，可见性不变）。
- 2026-11-09：每个 skill 在 `skills/<skill名>/` 下自包含，自带 `tests/`、`docs/`、`references/`；根目录只留库级文件。
- 2026-11-09：单 skill 的凭据配置、代理排查和状态码全表移入 `skills/git-auto-sync/references/setup.md`，SKILL.md 只留决策规则和导航。
- 2026-11-09：统一改名。本地文件夹改为 `Project_09_个人skill库`；GitHub 仓库由 `git-auto-sync-skill` 改为 `skillforge`（PUBLIC 不变，旧地址自动重定向）。库内 skill 名 `git-auto-sync` 不改。
- 2026-11-10：新增库根 `docs/skill制作SOP.md`，作为全库通用的 skill 制作流程。按六类（纪律约束、技术方法、思维模式、参考文档、脚本执行、素材模板）分叉验证方式，主干统一为立项判断、RED 失败场景、命名目录、写 SKILL.md、配套文件、GREEN 验证、开源门禁、部署迭代。做新 skill 前必读。
- 2026-11-10：git-auto-sync 第二轮优化，测试从 17 个增至 40 个，分六个独立提交：超时环境变量、认证误判收窄、porcelain -z 路径解析、暂存 diff 内容密钥扫描、push 错误分类且保留本地提交、回环代理端口探测。
- 2026-11-10：测试夹具结论：本地文件协议远程忽略 http.proxy，dumb HTTP 假服务器无法复刻真实 GitHub 的 401 文本。错误分类正确性靠纯函数测试，集成测试只锁“push 失败必须保留本地提交”。真实 GitHub 行为见 `skills/git-auto-sync/docs/e2e-手动清单.md`。
- 2026-11-10：集成测试用独立子进程跑 `sync.py`（`self.sync` 走 `subprocess`），测试进程里的 monkeypatch 传不进去，所以不能在 `SyncTests` 里 mock `detect_open_proxy_ports`。涉及机器环境（如本机代理端口是否在监听）的断言要收窄成各分支公共子串，具体分支文案交给同进程的 `ProxyPortProbeTests` 用 mock 确定性覆盖，否则在有代理的机器上会 flaky。
- 2026-11-10：第三轮优化加国内网络连接状态机，拆成 `network.py`（TCP 探测、直连重试、Windows 系统代理残留检测）、`proxy_pref.py`（代理偏好本地状态文件）、`connection.py`（状态机决策）、`network_adapter.py`（对接 sync.py）四个模块，测试从 40 个增至 83 个。
- 2026-11-10：状态机默认启用，`GIT_SYNC_NETWORK_STATE=0` 只作为显式关闭的逃生舱。最初实现成"设 1 才启用"，导致默认行为和“自动消化抖动”的目标脱节；改为默认启用后，所有测试夹具统一注入 `GIT_SYNC_TEST_DIRECT=success`，探测确定性成功、零真实联网，旧测试行为不变。
- 2026-11-10：子进程测试的网络隔离方案是环境变量注入：`GIT_SYNC_TEST_DIRECT` 控制直连成败、`GIT_SYNC_TEST_PROXY_ALIVE` 控制代理端口探测、`GIT_SYNC_TEST_SYSTEM_PROXY` 模拟系统代理、`GIT_SYNC_STATE_HOME` 把状态文件指到临时目录。适配层见到测试变量就走 fake，线上不设这些变量才用真实 socket 和注册表。
- 2026-11-10：系统代理残留判定看“开关是否开 + 指向端口有无服务”，端口无服务才叫残留，有服务但连不上归节点或规则问题。只检测不自动复位，复位方法写进 setup.md，不绑定具体代理软件品牌。
- 2026-11-10：第四轮优化补齐六项缺口。诊断新增 git `http.proxy/https.proxy` 和环境变量 `HTTP(S)_PROXY/ALL_PROXY` 两个只读字段，能力全部参数注入；直连探测改为每轮同时探 443 和 22，443 阻断但 22 通时 reasons 给 `ssh_available`。
- 2026-11-10：代理可用性分两层。先看端口存活，HTTP 代理再发 `CONNECT github.com:443`，2xx 才算隧道可用；SOCKS 第一版保守处理，只看端口不做握手。端口活但隧道失败返回 `proxy_node_failed`，在提交前拦回 `need_choice`，不再带坏代理走到 `push_failed`。
- 2026-11-10：重试间隔统一成 `random.uniform(1,2)`，生产用真实 `time.sleep`，测试通过注入 no-op sleep 保持快速。决策结果新增 `remote_risk`，非回环代理在使用前暴露凭据风险。
- 2026-11-10：`network_choice_required` 的回答方式固定为环境变量重跑：`GIT_SYNC_RETRY_DIRECT=1` 再试一轮，`GIT_SYNC_PROXY=<url>` 给代理，加 `GIT_SYNC_REMEMBER_PROXY=1` 同时记住。带 `GIT_SYNC_TEST_` 前缀的变量只用于测试注入，不写进用户文档。
- 2026-11-11：第五轮针对“陌生用户能不能顺利用”的评审做平台与协议补强，测试从 107 个增至 127 个，分两个独立提交。
- 2026-11-11：新增 `scripts/git_platform.py` 集中放平台识别和认证指引。Windows 保留 PowerShell 步骤，macOS/Linux 给通用终端指引并提示系统代理检测仅 Windows 可用；写死“打开 Windows PowerShell”的旧文案删除。SKILL.md 显式声明“当前仅 Windows 完整支持”，避免其他系统用户装了才发现一半能力缺失。
- 2026-11-11：启动闸门前置。`sync.main()` 在任何 git 操作前先跑 `dependency_check()`，PATH 无可用 git 直接返回 `missing_dependency`（新退出码 8），不产生提交。子进程测试靠 `GIT_SYNC_TEST_GIT_AVAILABLE` 注入，线上不设此变量才真实执行 `git --version`。
- 2026-11-11：SOCKS5 从“只看端口”升级为真实无认证握手。`network.socks5_tunnel` 先发方法协商（`05 01 00`，期望回 `05 00`），再发域名方式 CONNECT，回复码 `00` 才算节点可用；按协议分发的 `proxy_tunnel` 统一 HTTP CONNECT 和 SOCKS5 两条路径，`connection.proxy_usable` 对两类代理一视同仁，握手失败回 `need_choice` 并带 `proxy_node_failed`。
- 2026-11-11：跨平台兼容。`socket.recv_exactly` 是 Python 3.13 才有，改用内部 `_recv_exactly` 循环读定长字节，兼容更老的 Python 3。
- 2026-11-11：第六轮把“三败问答”从环境变量升级为命令行参数，测试从 127 个增至 138 个。新增 `--retry-direct`、`--proxy <url>`、`--remember-proxy` 三个 argparse 参数，经 `build_network_env` 合并进环境后再喂给状态机，`ConnectionPolicy` 和 `plan_connection` 一行不改，只换“输入从哪来”。
- 2026-11-11：参数优先级固定为命令行参数高于旧环境变量高于默认。旧的三个用户态变量（`GIT_SYNC_RETRY_DIRECT`、`GIT_SYNC_PROXY`、`GIT_SYNC_REMEMBER_PROXY`）保留读取做兼容，文档主推参数，老调用不会失效。带 `GIT_SYNC_TEST_` 前缀的仍是纯测试注入，不进文档。
- 2026-11-11：参数组合在任何 git 操作前校验。`--remember-proxy` 必须配 `--proxy`，`--retry-direct` 与 `--proxy` 互斥，违规直接返回 `invalid_arguments`（退出码 2），不产生提交。代理两道校验（端口存活加协议隧道）、`remote_risk`、带代理仍先首轮直连等安全语义全部沿用。

## 设计取舍
- 自动同步以“用户明确启用 + 当前分支 upstream”为边界；无远程时保留本地提交。
- 提交说明由 Codex 根据实际 diff 生成，不使用无信息量的固定模板。

## 踩坑记录
- Windows 下官方 `quick_validate.py` 默认按 GBK 读取中文；需设置 `PYTHONUTF8=1`，无需安装依赖。
- Windows Git 输出可能使用本地编码；执行器统一设置 `LC_ALL=C.UTF-8` 和 UTF-8 JSON 输出。
- 本地 bare 测试远程必须设置 `HEAD` 指向 `main`，否则 clone 没有工作树，远程分叉测试也会失真。
- 2026-11-10 代理实测：HTTP 代理 `127.0.0.1:20891` 端口在监听，但对 GitHub HTTPS 连续两次报 TLS unexpected eof；改用 `socks5h://127.0.0.1:7894`（同进程监听）一次成功。核对远程用 `git -c http.proxy=socks5h://127.0.0.1:7894 -c https.proxy=socks5h://127.0.0.1:7894 ls-remote origin`。全局 gitconfig 仍指向失效的 20890，是否统一改端口等用户拍板，执行器不自动改。
- 2026-11-11：写 SOCKS5 假服务器测试时连续踩三个协议细节。一是问候报文是 3 字节（版本+方法数+各方法），只 `read(2)` 会把方法字节留在缓冲区导致后续全部错位；二是 CONNECT 请求固定头是版本、命令、保留 3 字节，地址类型在第 4 字节，误把保留字节当 atyp 会按 IPv6 读 16 字节直到超时；三是 TCP 的 `recv(n)` 不保证一次收满，生产侧必须循环读定长，假服务器回复前要 `flush` 并开 `daemon_threads`，否则客户端可能在回复送达前就关闭连接。
- 2026-11-11：测试工具函数 `git()` 对输出做了 `strip()`，断言 `git status --porcelain` 这类带前导空格的原始输出时要绕过它，直接用 `subprocess.run` 取未裁剪文本，不能想当然补空格。

## 当前进度
- 2026-11-04：现用 `git-init` 已加入自动提交推送规则并通过官方格式校验。
- 2026-11-04：开源版执行器与文档完成，15 个项目测试和 4 个独立安全补测通过。
- 2026-11-04：双视角最终审查均为 PASS；已修复预暂存混入、敏感目录残留、首次推送强推/重定向等问题。
- 2026-11-04：公开仓库 `zyx1216/git-auto-sync-skill` 已发布并推送至 `7589bd0`。
- 2026-11-09：目录改造完成，`test_sync.py` 路径常量改为 `SKILL_DIR = parents[1]`，17 个测试在新路径全部通过。
- 2026-11-10：第二轮优化 8 个提交全部到达远程。`git ls-remote` 确认 `zyx1216/skillforge` 的 `HEAD` 和 `refs/heads/main` 都是 `ffc6e90`，与本地一致，工作区干净无 ahead。E2E 场景 1 的公开远程链路部分已覆盖，执行器直连 GitHub 的完整 `pushed` 链路仍待实测，详见 `skills/git-auto-sync/docs/e2e-手动清单.md`。

## 我的纠正（用户反馈）
- 用户要的是 Codex 完成任务后自动 commit + push，不是文件保存监听。
- 2026-11-04：必须提供 GitHub 凭据预配置流程；未配置时由 Codex 返回配置提醒，不能只在 push 失败后给原始报错。
- 2026-11-04：增加 HTTPS/SSH 配置文档与提交前 `authentication_required` 预检；16 项测试通过。
- 2026-11-04：首次上传必须分别确认仓库名和公开/私有，不能默认公开；建议英文短横线命名、优先私有。
- 2026-11-04：公开仓库 `zyx1216/git-auto-sync-skill` 已发布；首次推送遇到失效代理，因此其他人遇到时需返回代理排查和一次性手动直连说明，不自动改代理。

## 重要外部资源
- 参考项目：`juandelossantos/another-agent-skills`、`hyonchoi/git-atomic-commits`、`charlesjones-dev/ai-agent-plugins`。
- skill 结构规范：本机 `skill-creator` skill 的 SKILL.md（frontmatter、scripts/references/assets 约定、quick_validate.py）。
- 测试新路径：`skills/git-auto-sync/tests/test_sync.py`；运行入口在仓库根目录，discover 路径为 `skills/git-auto-sync/tests`。
