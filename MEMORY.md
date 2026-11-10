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

## 设计取舍
- 自动同步以“用户明确启用 + 当前分支 upstream”为边界；无远程时保留本地提交。
- 提交说明由 Codex 根据实际 diff 生成，不使用无信息量的固定模板。

## 踩坑记录
- Windows 下官方 `quick_validate.py` 默认按 GBK 读取中文；需设置 `PYTHONUTF8=1`，无需安装依赖。
- Windows Git 输出可能使用本地编码；执行器统一设置 `LC_ALL=C.UTF-8` 和 UTF-8 JSON 输出。
- 本地 bare 测试远程必须设置 `HEAD` 指向 `main`，否则 clone 没有工作树，远程分叉测试也会失真。

## 当前进度
- 2026-11-04：现用 `git-init` 已加入自动提交推送规则并通过官方格式校验。
- 2026-11-04：开源版执行器与文档完成，15 个项目测试和 4 个独立安全补测通过。
- 2026-11-04：双视角最终审查均为 PASS；已修复预暂存混入、敏感目录残留、首次推送强推/重定向等问题。
- 2026-11-04：公开仓库 `zyx1216/git-auto-sync-skill` 已发布并推送至 `7589bd0`。
- 2026-11-09：目录改造完成，`test_sync.py` 路径常量改为 `SKILL_DIR = parents[1]`，17 个测试在新路径全部通过。

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
