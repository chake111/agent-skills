# 提交链路（从本地改动到开 PR）

前面四个阶段的产出都在本地，这一节负责把它变成一个真能评审的 PR。**没有这一节，`git push` 没有落脚点。**

## 开工前：把贡献门槛抄进卡片

读默认分支的 `CONTRIBUTING.md` 与 `.github/`，往任务卡「贡献门槛」写四行，缺一行就补：

- CLA / DCO：要不要签、什么时候签（有些仓库开 PR 后才弹签署提示）
- AI 辅助声明：是否要求声明、要求包含什么（例如「已审阅生成的代码」）
- 目录约束：哪些目录的改动会被接受
- 交互要求：UI 改动是否要截图或录屏

读不到就写「未找到，按通用规范处理」，不要假设没有。

## 步骤

```bash
# 0. 确认默认分支与上游
gh repo view <owner>/<repo> --json defaultBranchRef,isFork

# 1. fork 并把 fork 加成 remote（首次贡献才需要；已在本地 clone 里执行）
gh repo fork <owner>/<repo> --clone=false --remote=true

# 2. 从核实过的基线切分支，命名跟随仓库近期习惯
git fetch origin
git switch -c <type>/<slug> <base_sha>

# 3. 应用改动、提交（仓库启用 DCO 时加 -s）
git add -A
git commit -m "<type>(<scope>): <subject>"      # DCO 仓库用 git commit -s

# 4. 推到 fork，不是上游
git push -u fork HEAD

# 5. 开 PR
gh pr create --repo <owner>/<repo> \
  --base <default-branch> \
  --head <你的用户名>:<branch> \
  --title "<与 commit 同风格>" \
  --body-file pr-body.md
```

`gh pr create` 返回的链接立刻写进任务卡与台账（`pr`、`pr_url`、`status=pr-open`）。

## CLA 的顺序

**先开 PR，再签 CLA。** 多数仓库（含 presenton）的 CLA 提示在 PR 创建后由 bot 触发，签署与评审并行；把「签完才能开 PR」当成前置，会让贡献白白停摆。

真正需要本人做的只是签署动作本身，这一条属于停点 A；开 PR、推分支、发评论都不属于。

## 提交信息与体量

- 风格跟随 `git log --oneline -20` 的实际写法，不套用 Conventional Commits 除非仓库在用。
- 单个 PR 控制在 300 行以内；超出就在卡片写拆分点，或写一行「为何不拆」。

## 失败处理

- **CI 红**：先分清环境问题与真实失败。本地跑不全的用例，在 PR 里说明哪些跑了、哪些没跑，不要沉默。
- **分支落后 base**：`git fetch origin && git rebase origin/<default>`，冲突解决后 `git push --force-with-lease fork HEAD`（只 force 自己的分支）。
- **PR 被 close**：把台账状态改成 `closed`，在卡片记关闭原因，判断是换方向还是补足后重开。
