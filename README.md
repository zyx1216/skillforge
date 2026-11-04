# git-auto-sync-skill

让 Codex 在完成项目修改后，自动验证、生成中文提交说明、提交相关文件并推送到当前分支的 upstream。

它不是文件监听器。Codex 未运行时不会同步，也不会因为你手动保存文件而自动提交。

## 功能

- 只提交当前任务相关路径，避免混入无关改动。
- 已有暂存内容或任务文件原本就有未提交改动时停止，不自动拆分或覆盖用户改动。
- Codex 在验证失败时不调用执行器；无改动、敏感文件、无 upstream 或推送失败时执行器给出明确状态。
- 本地提交与远程推送分别汇报。
- 禁止强推，不自动 merge/rebase，不擅自创建或修改远程仓库。
- Python 3 标准库执行器，无第三方运行时依赖。

## 安装

将 `skills/git-auto-sync` 整个目录复制到 `~/.codex/skills/`，然后重启 Codex。

在目标项目中说：

```text
使用 $git-auto-sync。今后每次完成修改并验证后，自动提交相关文件并推送当前分支。
```

首次使用前，确认当前分支的远程。已有 upstream 时直接推送；没有 upstream 且唯一远程为 `origin` 时，会建立当前同名分支的 upstream。其他情况保留本地提交并停止，不会自行创建 GitHub 仓库。

## 工作方式

Codex 负责判断任务是否完成、检查 diff、运行验证和撰写中文提交说明。`scripts/sync.py` 负责可重复验证的 Git 操作。

```bash
python "<skill目录>/scripts/sync.py" --message "feat: 添加用户登录" --allow-dirty -- src/login.py tests/test_login.py
```

`--allow-dirty` 表示你已确认传入路径的改动均由本任务产生，不会绕过全仓库预暂存检查。在目标仓库根目录运行，脚本路径使用安装后的绝对路径。

可能状态：`pushed`、`no_changes`、`missing_upstream`、`blocked_sensitive_path`、`push_failed`、`git_error`、`invalid_arguments`、`preexisting_staged_changes`、`preexisting_dirty_paths`。

沙箱和命令审批仍然有效。GitHub 凭据使用你已有的 Git 配置，本项目不会读取或保存 Token。

## 测试

```bash
python -m unittest discover -s tests -v
```

在完整源码仓库根目录运行测试。测试在临时目录创建真实 Git 仓库与 bare 远程，覆盖首次 upstream、后续推送、无改动、敏感路径、无 upstream 和远程分叉，不访问真实 GitHub 仓库。验证失败由 Codex 在调用前拦截，不属于执行器测试。

## 限制

- 敏感文件名检查不是完整的密钥扫描。
- 保护分支或需要 PR 审查的仓库不应直接自动推送。
- 网络、认证和远程分叉需要用户处理，执行器不会强推。

## 许可证

MIT，见 `LICENSE`。
