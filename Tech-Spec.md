# Git 自动同步 Skill · Tech Spec

## 方案

采用声明式 Codex skill 加可选 Python 标准库执行器。`SKILL.md` 定义触发条件、验证职责和提交说明规则；`sync.py` 负责确定性的 Git 状态检查、提交和推送。

需求发生在 Codex 完成任务的节点，不需要常驻进程。脚本不能替代 Codex 判断任务完成、验证通过或撰写提交说明，因此只接管可确定测试的 Git 操作。

## 同步流程

1. 确认用户已启用自动同步，并识别项目已有测试和验证方式。
2. 修改前运行 `git status`。存在预暂存内容或任务文件已有未提交改动时停止，不自动拆分同一文件中的用户与 Agent 改动。
3. 修改后运行 `git status --short` 和 `git diff`，无改动则结束。
4. 检查待提交路径及 diff 中的疑似凭据；命中时停止并让用户判断。
5. 运行项目已有验证；验证失败则保留改动，不提交、不推送。
6. Codex 根据 diff 生成中文 Conventional Commit 说明，并只传入本次任务相关路径。
7. 执行器复查敏感路径和 Git 状态，并用 `git ls-remote` 做只读凭据/远程预检；未认证时返回配置提醒且不提交，随后创建本地提交并记录哈希。
8. 执行器查询 `@{upstream}`；唯一远程为 `origin` 且当前为具名分支时建立同名 upstream，其他情况保留本地提交并报告。
9. 执行器运行 `git push`，分别汇报提交与推送状态；失败时不强推、不自动整合远程。

## 测试策略

- 结构测试：frontmatter、目录命名、无占位符、README 与规则一致。
- 行为测试：在临时目录建立工作仓库和 bare 远程，覆盖首次 upstream 推送与后续推送。
- 停止条件测试：无改动、无 upstream、验证失败、敏感路径、远程分叉。
- 测试只操作临时目录，所有测试结束清理，不访问真实远程。

## 文件结构

```text
skills/git-auto-sync/SKILL.md
skills/git-auto-sync/agents/openai.yaml
tests/test_skill.py
skills/git-auto-sync/scripts/sync.py
README.md
LICENSE
PRD.md
Tech-Spec.md
```

## 发布门槛

格式校验和全部测试通过；Git/发布视角与 Skill 工程视角均通过；用户确认公开仓库可见性和最终推送。
