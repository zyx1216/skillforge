# Git Auto Sync Implementation Plan

**Goal:** 发布一个可测试的 Codex skill，在任务验证后提交并推送当前分支。

**Architecture:** Codex 负责验证、审阅 diff 和生成中文提交说明；Python 标准库执行器负责暂存指定路径、敏感路径拦截、提交与 upstream 推送。

**Tech Stack:** Markdown、Python 3 标准库、Git、unittest。

**Spec:** `Tech-Spec.md`

## Global Constraints

- 不监听文件，不常驻运行，不绕过 Codex 命令审批。
- 不强推，不自动 merge/rebase，不自动创建或修改远程。
- 只提交调用方明确传入的路径，默认推送当前分支 upstream。

### Task 1: 同步执行器

**Files:**
- Create: `skills/git-auto-sync/scripts/sync.py`
- Test: `tests/test_sync.py`

- [x] 写真实临时仓库测试并确认因缺少执行器而失败。
- [x] 实现状态检查、指定路径暂存、中文提交、首次 upstream 和后续推送。
- [x] 覆盖无改动、敏感路径、无 upstream、远程分叉与空路径。
- [x] 重跑全部测试并确认通过。

### Task 2: Skill 与发布材料

**Files:**
- Create: `skills/git-auto-sync/SKILL.md`
- Create: `skills/git-auto-sync/agents/openai.yaml`
- Create: `README.md`
- Create: `LICENSE`

- [x] 写明 Codex 先验证再调用执行器，不把脚本当作后台监听。
- [x] 提供 `$git-auto-sync` 安装与启用示例。
- [x] 运行官方格式校验和 Markdown 链接检查。

### Task 3: 发布验证

**Files:**
- Modify: `MEMORY.md`

- [x] 运行完整测试和格式校验。
- [x] 由 Git/发布与 Skill 工程两个独立视角审查，修复阻断问题后复审。
- [ ] 用户确认后创建公开 GitHub 仓库并推送。
