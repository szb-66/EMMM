# Triage Labels

技能内部使用五个标准 triage 角色。此文件将这些角色映射到本仓库实际使用的标签字符串。

| 技能中的标签               | 本仓库标签             | 含义                         |
| -------------------------- | ---------------------- | ---------------------------- |
| `needs-triage`             | `needs-triage`         | 维护者需要评估此 issue       |
| `needs-info`               | `needs-info`           | 等待提交者补充更多信息       |
| `ready-for-agent`          | `ready-for-agent`      | 规格明确，AI agent 可直接接手 |
| `ready-for-human`          | `ready-for-human`      | 需要人类来实现               |
| `wontfix`                  | `wontfix`              | 不会处理                     |

当技能提到某个角色时，使用此表中对应的标签字符串。

## 创建标签

如果 GitHub 仓库尚未配置这些标签，运行：

```bash
gh label create "needs-triage" --description "Maintainer needs to evaluate this issue" --color "D4C5F9"
gh label create "needs-info" --description "Waiting on reporter for more information" --color "BFD4F2"
gh label create "ready-for-agent" --description "Fully specified, ready for an AFK agent" --color "C2E0C6"
gh label create "ready-for-human" --description "Requires human implementation" --color "FEF2C0"
gh label create "wontfix" --description "Will not be actioned" --color "D3D3D3"
```
