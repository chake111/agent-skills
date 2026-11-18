# agent-skills

我自己的 AI Agent skill 合集，四个都在日常使用，不收录第三方项目。

每个 skill 是一个带 YAML frontmatter 的 `SKILL.md`，放进 agent 的 skills 目录就能用日常说法触发。

| Skill | 用途 | 路径 |
| --- | --- | --- |
| [boss-daily-apply](skills/boss-daily-apply/SKILL.md) | 在 BOSS直聘 上按天批量投递对口的实习岗 | `skills/boss-daily-apply/` |
| [oss-contribution](skills/oss-contribution/SKILL.md) | 从筛项目到开 PR，推进一次完整的开源贡献 | `skills/oss-contribution/` |
| [resume-competitiveness](skills/resume-competitiveness/SKILL.md) | 围绕具体求职目标诊断简历竞争力 | `skills/resume-competitiveness/` |
| [video-subtitle](skills/video-subtitle/SKILL.md) | 提取视频字幕，没有字幕时走语音转写 | `skills/video-subtitle/` |

## 四个 skill

### boss-daily-apply

按天在 BOSS直聘 上批量投实习岗：先探供给，按简历证据强度分配方向，再一张一张读 JD、语义判断是否对口、当场投递，随后补发这一份的简历图和按方向写的一句话，收尾出汇总页与回复台账。该不该投由运行本技能的智能体读 JD 后判断，判定依据是本地工作目录里的个人档案，代码里没有筛选规则。需要 Python 3.9+ 和任意 Chromium 系浏览器，默认走内置 CDP，Playwright 与 Kimi WebBridge 是可选回退。

### oss-contribution

把一次开源贡献从选项目推进到 PR：项目筛查、机会调研、方案设计、受控实现、审查分级、提交链路、PR 文案。全程自主决策，只在法律签署、账号凭据、不可逆地影响他人、信息缺口这四类情况下停下来问。每次贡献的结论、证据和下一步记在本地任务卡与台账里，换会话可以接着做。发布与状态核查使用已登录的 `gh`。

### resume-competitiveness

围绕目标岗位、职级、城市和薪资判断简历的竞争力。从基础竞争力、差异化竞争力、能力证明三个维度给结论，把问题分成表达、证据、能力、定位四类，每类对应不同动作，改简历只对表达问题有效。会审查 2–4 个核心项目的证据缺口，给出 P0/P1/P2 行动清单；有投递数据时，用固定变量的方式设计下一轮验证。不编造经历和数字，也不把“简历里没写”当成“不具备”。

### video-subtitle

提取并转写字幕，覆盖 YouTube、B站、抖音、小红书以及其他 yt-dlp 支持的站点。先取人工或自动字幕；确实没有字幕轨时只下载音轨，交给 AudioTranscribe 或 Whisper 转写，再把结果统一成带起止时间的片段。可导出 TXT、SRT、Markdown 和统一的 segments JSON。只处理公开内容，不下载完整视频，不绕过登录、付费、地区或 DRM 限制。

## 安装

```bash
git clone https://github.com/chake111/agent-skills.git
```

Windows（PowerShell，`-Target` 默认是 `$HOME\.agents\skills`）：

```powershell
.\agent-skills\scripts\install.ps1 -Target "$HOME\.agents\skills"
```

macOS / Linux：

```bash
./agent-skills/scripts/install.sh ~/.agents/skills
```

两个脚本都在目标目录里为每个 skill 建目录链接，已经存在的条目会跳过并提示。也可以手工建链接，效果一样：

```bash
ln -s "$PWD/agent-skills/skills/boss-daily-apply" ~/.agents/skills/boss-daily-apply
```

链接而不是复制，`git pull` 之后所有客户端拿到的都是同一份。ZCode 读 `~/.agents/skills/`；Claude Code 用 `~/.claude/skills/`，其他客户端换成各自的 skills 目录。装好后新开一个会话，客户端会重新扫描。

## 仓库结构

```
skills/
├── boss-daily-apply/
│   ├── SKILL.md
│   ├── scripts/          # 投递、探供给、渲染简历图
│   ├── references/       # 判定标准、踩坑手册、逐岗位定制
│   └── config/           # 黑名单、招呼语、档案模板
├── oss-contribution/
│   ├── SKILL.md
│   ├── references/       # 筛查、调研、设计、实现、审查、提交、PR 文案
│   └── assets/
├── resume-competitiveness/
│   ├── SKILL.md
│   └── agents/
└── video-subtitle/
    ├── SKILL.md
    ├── scripts/
    └── tests/
scripts/                  # install.ps1 / install.sh
```

## 隐私

仓库里没有个人档案、简历照片、二维码或投递记录，只有 skill 的说明、脚本和示例配置。

需要个人信息的部分在运行时生成本地文件：boss-daily-apply 会把档案、投递记录和简历图写在本地工作目录（默认 `~/.boss-daily-apply`），这些路径已在 `.gitignore` 里排除，不会进入版本库。二维码图只有本地存在时才嵌进报表。

## 许可

[MIT](LICENSE)