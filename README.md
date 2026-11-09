# zyx-codex-skills

我个人开发的 Codex skill 合集，全部开源。每个 skill 放在 `skills/` 下的独立目录，文件自包含，可以整个目录复制到本地 skills 目录使用。

## Skill 索引

| Skill | 干什么 | 目录 |
| --- | --- | --- |
| `git-auto-sync` | Codex 完成任务并验证后，按实际改动生成中文提交说明，只提交本任务相关文件并推送到当前分支的 upstream | [`skills/git-auto-sync/`](skills/git-auto-sync/SKILL.md) |

## 目录结构

```text
.
|-- AGENTS.md            库级开发规则
|-- README.md            本文件，库首页和 skill 索引
|-- MEMORY.md            架构决策和踩坑记录
|-- LICENSE              全库统一 MIT
`-- skills/
    `-- <skill名>/
        |-- SKILL.md     技能说明（必需）
        |-- agents/      UI 元数据（按需）
        |-- scripts/     辅助脚本（按需）
        |-- references/  按需加载的文档（按需）
        |-- tests/       该 skill 自己的测试
        `-- docs/        该 skill 的 PRD、技术规格、复盘
```

## 安装单个 skill

把 `skills/<skill名>/` 整个目录复制到本机的 `~/.codex/skills/`，然后重启 Codex。

以 git-auto-sync 为例：

```powershell
Copy-Item -Recurse 'skills\git-auto-sync' "$HOME\.codex\skills\git-auto-sync"
```

安装后在目标项目里说：

```text
使用 $git-auto-sync。今后每次完成修改并验证后，自动提交相关文件并推送当前分支。
```

## git-auto-sync 快速说明

它只在 Codex 会话内、任务完成并验证通过后工作。Codex 没运行时不会同步，手动保存文件也不会触发提交，它不是文件监听器。

推送需要本机已经配好 GitHub 凭据，skill 不保存也不读取密码或 Token，只复用本机 Git 凭据。首次使用前的 HTTPS/SSH 配置步骤、代理排查和全部返回状态，见 [`skills/git-auto-sync/references/setup.md`](skills/git-auto-sync/references/setup.md)。

主要安全行为：

- 只提交传入的任务相关路径，暂存区已有其他改动时直接停止，不覆盖用户改动。
- 发现 `.env`、私钥或凭据文件时停止，不自动提交。
- 禁止强推，不自动 merge 或 rebase，远程分叉时保留本地提交并报错。
- 没有 upstream 时只在唯一远程为 `origin` 的情况下建立同名 upstream，其他情况保留本地提交。
- 不自动创建、改名 GitHub 仓库，也不自动改公开或私有状态；新建仓库前分别确认仓库名和可见性。

执行器只用 Python 3 标准库，没有第三方运行时依赖。

## 开发与测试

在仓库根目录跑某个 skill 的测试（Windows 必须加 UTF-8 环境变量，否则中文按 GBK 解码报错）：

```powershell
$env:PYTHONUTF8='1'; D:\Anaconda\python.exe -m unittest discover -s skills/git-auto-sync/tests -v
```

测试在临时目录创建真实 Git 仓库和本地 bare 远程，不访问真实 GitHub。

校验 skill 格式：

```powershell
$env:PYTHONUTF8='1'; D:\Anaconda\python.exe C:\Users\zyx\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/git-auto-sync
```

## 贡献与安全

这是个人项目，目前不接受外部 PR。任何人使用前都应先读 `SKILL.md` 和 `references/`，确认行为符合自己的仓库策略。

本仓库全程公开，历史提交里不接受任何凭据。如果发现密钥被提交，立即吊销该密钥，不要只靠删除文件处理，因为 Git 历史里仍有记录。

## 许可证

MIT，见 `LICENSE`。
