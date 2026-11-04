# git-auto-sync-skill

让 Codex 在完成项目修改后，自动验证、生成中文提交说明、提交相关文件并推送到当前分支的 upstream。

它不是文件监听器。Codex 未运行时不会同步，也不会因为你手动保存文件而自动提交。

## 前置配置 GitHub 凭据

不需要把 GitHub 密码或 Token 提供给 Codex，skill 只复用本机已有凭据。

### HTTPS（推荐）

以下命令都在 **Windows PowerShell** 中执行，不是在 Codex 对话框里发送。按 `Win + R`，输入 `powershell` 并回车即可打开。命令与当前目录无关，不需要先 `cd` 到项目。

1. 在 PowerShell 运行 `gh --version`。如果提示找不到 `gh`，先安装 GitHub CLI，再重新打开 PowerShell。
2. 在同一个 PowerShell 窗口运行：

   ```powershell
   gh auth login
   ```

3. 按窗口中的问题依次选择 `GitHub.com`、`HTTPS`、浏览器登录。窗口显示一次性验证码后，复制验证码，在自动打开的 GitHub 网页中登录并授权。
4. 回到 PowerShell，登录成功后运行：

   ```powershell
   gh auth setup-git
   ```

   这条命令让本机 Git 在推送时复用刚才的 GitHub 登录凭据。

5. 最后运行 `gh auth status`，看到已登录账号即完成。以后 Codex 执行 `git push` 时会使用这套凭据。

### SSH

SSH 命令同样在 Windows PowerShell 中执行。

1. 在本机生成或复用 SSH 密钥，并把公钥添加到 GitHub 账号的 `Settings → SSH and GPG keys`。
2. 确认仓库远程使用 SSH 地址，例如 `git@github.com:用户名/仓库.git`。
3. 运行 `ssh -T git@github.com` 验证连接。

未配置、凭据失效或账号无权限时，执行器会在提交前返回 `authentication_required` 和配置提醒，不会要求你发送密码或 Token。Codex 会明确提醒你在 Windows PowerShell 中完成上述步骤。

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

### 首次上传的命名与可见性

还没有 GitHub 仓库时，Codex 会分别问你：

1. **仓库名**：建议使用英文小写和短横线，例如 `emg-action-recognition`。本地目录仍可叫 `Project_01_emg毕设`，两者不必相同，README 可写中文项目名。
2. **公开还是私有**：建议先选私有，确认代码和文档可以公开后再改为公开。公开仓库任何人都可能看到，不能仅凭“开源发布”几个字默认创建。

只有两项都明确后，Codex 才能创建远程仓库。已有仓库不会被自动改名或改变公开/私有状态；推送结果会包含完整仓库地址和可见性。

## 工作方式

Codex 负责判断任务是否完成、检查 diff、运行验证和撰写中文提交说明。`scripts/sync.py` 负责可重复验证的 Git 操作。

```bash
python "<skill目录>/scripts/sync.py" --message "feat: 添加用户登录" --allow-dirty -- src/login.py tests/test_login.py
```

`--allow-dirty` 表示你已确认传入路径的改动均由本任务产生，不会绕过全仓库预暂存检查。在目标仓库根目录运行，脚本路径使用安装后的绝对路径。

可能状态：`pushed`、`no_changes`、`missing_upstream`、`authentication_required`、`remote_unavailable`、`blocked_sensitive_path`、`push_failed`、`git_error`、`invalid_arguments`、`preexisting_staged_changes`、`preexisting_dirty_paths`。

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
