---
name: git-auto-sync
description: 在 Codex 完成项目修改并验证后，根据实际改动生成中文提交说明，提交指定文件并推送到当前分支的 upstream。用户要求启用自动 Git 提交、同步或推送时使用；不用于文件保存监听、后台定时同步、强制推送或自动解决冲突。
---

# Git 自动同步

用户明确启用后，在每次任务完成时同步代码。此 skill 只在 Codex 会话内运行，不会监听文件，也不会在 Codex 未运行时推送。

## 前置条件

本机必须已有 GitHub 推送凭据。HTTPS 推荐先运行 `gh auth login`，按提示选择 GitHub.com、HTTPS 和浏览器登录，再运行 `gh auth setup-git`；SSH 用户需提前配置密钥并用 `ssh -T git@github.com` 验证。不得要求用户把密码或 Token 发给 Codex。

## 执行流程

1. 修改前运行 `git status`。已有任何暂存内容，或本任务将修改的文件已有未提交改动时，停止自动同步并让用户先拆分或提交；不要保存、清空或重写用户索引。
2. 修改后运行 `git status --short` 和 `git diff -- <本任务路径>`。没有实际改动则结束，不创建空提交。
3. 检查待提交路径和 diff，不读取或输出凭据内容。发现 `.env`、私钥、凭据文件或疑似密钥时停止并让用户判断。
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
   - `missing_upstream`：本地提交已保留，提示用户配置远程；不要自行创建仓库或修改远程。
   - `authentication_required`：预检发现未登录、凭据失效或账号无权限，向用户展示 `setup` 中的配置步骤；此状态在提交前返回，不得索要 Token。
   - `remote_unavailable`：远程地址不存在、网络不可用或无法确认权限，展示脱敏错误并让用户检查地址与网络。
   - `blocked_sensitive_path`：敏感文件未提交，告知用户具体路径。
   - `push_failed`：本地提交已保留，报告 Git 错误；不要强推，不要自动 merge 或 rebase。
   - `preexisting_staged_changes` / `preexisting_dirty_paths`：用户已有改动需要人工拆分，不要绕过检查。
   - `git_error`：报告失败命令的错误摘要，不声称已经同步。
   - `invalid_arguments`：补齐提交说明和仓库内相对路径后重试。

## 安全边界

- 已有 upstream 时只推送当前分支的 upstream。没有 upstream 时，仅在远程列表唯一为 `origin`、当前为具名分支且 `origin` 可访问时，执行 `git push -u origin <当前分支>`；其他情况保留本地提交并停止。
- 禁止 `--force`、`--force-with-lease` 和其他改写远程历史的操作。
- 不自动重试认证或网络失败；最多由用户判断后重新执行。
- 沙箱或命令审批要求用户批准时，正常请求批准，不尝试绕过。
- 保护分支或需要 Pull Request 的仓库不启用直接推送，改为提交后提示用户走 PR。
- 路径检查只能减少误提交，不能代替完整密钥扫描。
- 执行器不会保存或恢复用户暂存区；存在预暂存内容时直接停止，避免误提交或破坏索引。

## 汇报

分别报告本地提交哈希和推送状态。没有 upstream 或推送失败时，明确说“本地已提交，GitHub 未更新”，不得把 commit 当成 push 成功。
