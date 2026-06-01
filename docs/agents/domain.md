# Domain Docs

Engineering skills 在探索代码库时应如何获取领域文档。

## 探索前，读取以下文件

- **`CONTEXT.md`**（仓库根目录）— 领域词汇表和核心概念定义
- **`docs/adr/`** — 跨 feature 的架构决策记录（单次 feature 决策见 `openspec/changes/*/design.md`）
- **`openspec/specs/`** — 按层组织的技术规格，是系统当前行为的真相来源。读取与你工作范围相关的 spec 文件

如果以上任何文件不存在，**静默跳过**。不要提示缺失，不要建议创建。相关 producer skill（`/grill-with-docs`）会在术语或决策实际确定时懒创建它们。

## 文件结构

单上下文仓库：

```
/
├── CONTEXT.md              ← 领域词汇表
├── docs/adr/               ← 跨 feature 架构决策
│   ├── 0001-xxx.md
│   └── 0002-xxx.md
├── openspec/specs/         ← 技术行为规格（按层组织）
│   ├── core.md
│   ├── models.md
│   ├── viewmodels.md
│   ├── views.md
│   └── services.md
└── src/
```

## 使用词汇表的术语

当你的输出涉及领域概念时（issue 标题、重构提案、测试名称），使用 `CONTEXT.md` 中定义的术语。不要漂移到词汇表明确避免的同义词。

如果你需要的概念不在词汇表中，这是个信号 — 要么你创造了项目不用的语言（重新考虑），要么存在真正的缺失（记下来供 `/grill-with-docs` 处理）。

## 标记 ADR/OpenSpec 冲突

如果你的输出与现有 ADR 或 OpenSpec spec 矛盾，显式标注出来，而非静默覆盖：

> _与 ADR-0007（event-sourced orders）矛盾 — 但值得重新讨论，因为…_
