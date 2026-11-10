# 个人 AI 自制 Skill 库 · AGENTS.md

## 项目定位
- 本仓库是邹宇轩个人开发的 Codex skill 合集，全程开源公开。远程为 `zyx1216/skillforge`（PUBLIC），分支 `main`。旧名 `git-auto-sync-skill` 已于 2026-11-09 改名，GitHub 自动重定向旧地址。
- 每个 skill 单独放在 `skills/<skill名>/` 子目录，文件自包含，可以整个目录复制安装。
- 当前收录：`git-auto-sync`，在 Codex 完成任务并验证后生成中文提交说明、提交相关文件并推送当前分支。

## 目录结构
- `skills/<skill名>/` 放一个 skill 的全部文件：
  - `SKILL.md`：必需，含 YAML frontmatter 的技能说明。
  - `agents/openai.yaml`：UI 元数据和调用策略，按需创建。
  - `scripts/`：可执行辅助脚本，按需创建。
  - `references/`：按需加载的文档，例如配置和排障手册。
  - `tests/`：这个 skill 自己的测试。
  - `docs/`：这个 skill 的 PRD、技术规格、复盘等开发文档。
- 根目录只放库级文件：`AGENTS.md`、`MEMORY.md`、`README.md`、`LICENSE`、`.gitignore`。新增 skill 在 `skills/` 下建子目录，不在根目录散放文件。
- 库根 `docs/` 放全库通用文档，当前有 `skill制作SOP.md`，规定各类型 skill 从立项到发布的统一流程；skill 自己的 PRD、复盘仍放它内部的 `docs/`。
- 做新 skill 或大改老 skill 前，先按 `docs/skill制作SOP.md` 走，先写失败场景再写 skill，按类型选验证方式。

## 公开仓库安全规则（硬规则）
- 本库全程公开，每次提交前必须检查 diff，确认没有 `.env`、密钥、Token、私钥和个人敏感信息。
- 凭据只放环境变量或 `.env`；`.env` 已在 `.gitignore`，永远不提交。需要给配置模板时用 `.env.example`，只写变量名。
- 文档和示例里不写真实密码、Token、内部地址，一律用占位符。
- 不自动修改 GitHub 仓库可见性。当前公开状态已经用户确认；改私有、建新仓库或改名前必须再次确认。

## 常用命令（PowerShell，仓库根目录执行）
- 校验单个 skill：`$env:PYTHONUTF8='1'; D:\Anaconda\python.exe C:\Users\zyx\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\<skill名>`
- 跑某个 skill 的测试：`$env:PYTHONUTF8='1'; D:\Anaconda\python.exe -m unittest discover -s skills/<skill名>/tests -v`
- 必须设 `PYTHONUTF8=1`，否则 Windows 下中文按 GBK 解码会报错。

## 开发约定
- skill 命名只用小写字母、数字和短横线，64 字符以内，目录名和 skill 名保持一致。
- 新建或大改 skill 前先看 `skill-creator` 的结构规范。`SKILL.md` 只留做决策需要的内容，配置步骤、排障和长示例放 `references/`，需要时再读。
- 行为测试放在 skill 自己的 `tests/`，用临时目录和本地 bare 仓库，不访问真实 GitHub。
- 许可证统一用根目录的 MIT，skill 子目录不单独放 LICENSE，除非某个 skill 用了不同许可证。
- 提交说明用简体中文，写清改了什么、为什么，不用 `update`、`auto commit` 这类没有信息量的模板。
- 每个 skill 自己的业务规则写在它的 `SKILL.md` 和脚本里，不堆到本文件。例如 Git 禁止强推、不自动改代理、预暂存检查等规则属于 `git-auto-sync`。

## 发布说明
- 远程：`origin = https://github.com/zyx1216/skillforge.git`。
- 本机全局 gitconfig 配了 `127.0.0.1:20890` 代理，代理没启动时 push 会失败。确认能直连时用 `git -c http.proxy= -c https.proxy= push` 一次性绕过，不改全局配置，具体见 `skills/git-auto-sync/references/setup.md`。
- 未经用户确认，不发布 Release、不改仓库名和可见性。
