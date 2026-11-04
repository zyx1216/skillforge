# Git 自动同步 Skill · AGENTS.md

## 项目概览
- 目标：开发并开源 Codex skill，在 Codex 完成项目修改后自动验证、生成中文提交说明、提交并推送。
- 技术栈：Markdown、Codex Skill、Git、Python 标准库执行器与测试。
- 包管理器：无运行时第三方依赖；校验器使用 Anaconda 已有 PyYAML。

## 常用命令
- 校验：`$env:PYTHONUTF8='1'; D:\Anaconda\python.exe <skill-creator>\scripts\quick_validate.py <skill目录>`
- 测试：`D:\Anaconda\python.exe -m unittest discover -s tests -v`
- 发布：测试和双视角审查通过后，使用 `gh repo create` 创建公开仓库。

## 架构约定
- 正式 skill 放在 `skills/git-auto-sync/`，项目说明与开发文档不复制进 skill。
- 只做 Codex 会话内的任务后同步，不实现文件监听、后台服务或定时任务。
- `sync.py` 负责确定性的 Git 状态检查、提交和推送；Codex 负责验证、审阅 diff 和生成中文提交说明。
- 自动推送针对当前分支已有 upstream，或唯一远程为 `origin` 时建立同名 upstream；禁止强推和自动改写历史。

## 测试与验证
- 修改推送规则前，先用测试表达正常、无改动、无远程、验证失败、敏感文件和远程分叉场景。
- 推送测试使用临时本地 bare 仓库，不访问真实 GitHub 项目。
- 发布前完成 skill 格式校验、测试、安装说明检查和双视角审查。

## 发布说明
- GitHub 仓库名：`git-auto-sync-skill`。
- 许可证：MIT。
- 未经用户最终确认，不创建公开远程仓库、不发布 Release。
