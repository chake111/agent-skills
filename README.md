# agent-skills

我自己的 AI Agent skill 合集。

每个 skill 是一个带 YAML frontmatter 的 `SKILL.md`，放进 agent 的 skills 目录就能用日常说法触发。

| Skill | 用途 | 路径 |
| --- | --- | --- |
| [boss-daily-apply](skills/boss-daily-apply/SKILL.md) | 在 BOSS直聘 上按天批量投递对口的实习岗 | `skills/boss-daily-apply/` |
| [oss-contribution](skills/oss-contribution/SKILL.md) | 从筛项目到开 PR，推进一次完整的开源贡献 | `skills/oss-contribution/` |
| [resume-competitiveness](skills/resume-competitiveness/SKILL.md) | 围绕具体求职目标诊断简历竞争力 | `skills/resume-competitiveness/` |
| [video-subtitle](skills/video-subtitle/SKILL.md) | 提取视频字幕 | `skills/video-subtitle/` |

## 安装

```bash
git clone https://github.com/chake111/agent-skills.git
```

Windows：

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

## 许可

[MIT](LICENSE)
