# ADR 0001: ViewModels / Services 两层大文件 Mixin 化拆分

| | |
|---|---|
| **状态** | Accepted |
| **日期** | 2026-07-09 |
| **关联 spec** | `openspec/specs/viewmodels.md`、`openspec/specs/services.md` |

## 背景

EMMM 是单人 + AI 协作开发的 PyQt6 mod 管理器。进入修复「开关 mod 闪退 / 拖压缩包闪退」阶段后，单一文件频繁被多次跳改：

- `app/viewmodels/mod_list_vm.py` 达 **1910 行 / 100+ 方法**
- `app/services/mod_service.py` 达 **1486 行 / 36+ 方法**

七次崩溃修复期间平均每次 hotfix 都在这两个文件里横跳多个无关段落，diff 难审、回归难定位、AI 上下文持续爆炸。

## 决策

仅对 **viewmodels / services 两层** 触及的文件做 Mixin 化拆分：

- `ModListViewModel` → 包 `app/viewmodels/mod_list_vm/`，主类继承 7 个关注点 Mixin（load / filter / crud / creation / reconciliation / exclusive_activation / thumbnail）
- `ModService` → 包 `app/services/mod_service/`，主类继承 5 个 Mixin（load / toggle / crud / preview / creation）

### 选 Mixin 而非独立子服务的理由

- `main.py` 与所有外部 import 用 `from app.services.mod_service import ModService` —— 包 `__init__.py` 同名 re-export 让**外部 import 路径零改动**
- Mixin 共享 `self.<state>` 与 `self.<service>`，不需要在主体注入额外对象
- 此次为「纯搬运」目标：不动逻辑、不动信号契约、不动 main.py 配线，把行为风险降到最低

### Mixin 与 QObject 的两条强制约束

1. **`pyqtSignal` 必须在主体 QObject 子类声明**。pyqtSignal 是 Qt 描述符，把它放在 Mixin 会破坏 Qt 的元对象系统。Mixin 只放普通方法。
2. **Mixin 不定义 `__init__`**。MRO 中所有 Mixin 排在 QObject 之前但都不接 `__init__`，唯一构造点在主类。共享状态字段在主类 `__init__` 中初始化，Mixin 方法通过 `self.<attr>` 读写。

### MRO 顺序约定

`class ModListViewModel(_ThumbnailMixin, _ExclusiveActivationMixin, _ReconciliationMixin, _CreationMixin, _CrudMixin, _FilterMixin, _LoadMixin, QObject):`

- Mixin 顺序仅影响diamond 查找；目前 Mixin 间互调走 `self.<method>()` 鸭子类型，**不**互相 import 主类，因此实际无 diamond。
- Mixin 间互调借助 `self`，类型注解用 `TYPE_CHECKING` guard 引用主体类，避免运行时循环导入。

## 代价

- 跨文件读 `self` 状态需要查继承树定位方法所在 Mixin（IDE / 静态分析 still OK，但目录跳读增加）
- 每次新方法添加前需判断归属 Mixin；新增 import 时易遗漏（本次拆分即因此漏掉 `dataclasses` / `INFO_JSON_NAME` / `QImage` / `Image` / `os` 五项，被运行时 NameError 暴露）。建议加 `pytest --collect-only` 启动 smoke。
- ADR 已立此约束，「pyqtSignal 留主体」未来若被破坏会在运行时报 `TypeError`，编译期无保护，需实测验证。

## 不拆的边界

以下文件行数虽大，但**不**纳入本次拆分，理由如下：

| 文件 | 行数 | 不拆理由 |
|---|---|---|
| `preview_panel_vm.py` | 900 | 单一职责（预览面板状态机），内聚性高 |
| `main_window_vm.py` | 842 | 编排者，watcher 协调外提价值有限 |
| `Iniparsing_service.py` | 816 | 可在 Step 6 中考虑，本次不触 |
| `objectlist_panel.py` / `foldergrid_panel.py` / `thumbnail_widget.py` / `settings_dialog.py` / `main_window.py` | 532–742 | **视图**视觉连贯性优先于行数；/layouts/_init_ui 共享同一 widget 上下文 |
| `models/` 各 dataclass | — | 静态数据，无逻辑可拆 |
| `dialogs/*` | 100–600 | 单一职责对话框，已天然分文件 |

## 触发拆分的阈值

单 `.py` 文件 **> 600 行**触发评估。评估维度：
- 行数 + 方法数 + 关注点数（多关注点倾向拆）
- 是否存在「外部入口」（imports / signal / public API —— 有则优先 Mixin 而非子服务）
- 是否破坏视图视觉连贯性（视图例外）

## 验证手段

每个 Mixin 拆完后：

1. `python -m py_compile` 全部新文件
2. `python -c "from app.services.mod_service import ModService; from app.viewmodels.mod_list_vm import ModListViewModel"` smoke
3. 解决 NameError 的最稳妥方式：实际跑 `python main.py` 并操作对应流程（hydrate / toggle / 创建 / sync / drag-drop），任何遗漏 import 都会在用户路径下冒出
4. 检查 `logs/` 无新 Traceback

## 历史

- Step 1 `fe9834f`：mod_list_vm 拆 load + filter mixin（删原文件，建包）
- Step 2 …    ：mod_list_vm 加 5 mixin（crud / creation / reconciliation / exclusive / thumbnail）
- Step 4     ：mod_service 拆 5 mixin
- 修复 commit `64d8003`：补遗漏 imports（`dataclasses`、`INFO_JSON_NAME`、`QImage`、`Image`、`os`）

## 未来可能动作（未做决定）

- `preview_panel_vm.py`、`main_window_vm.py` 若未来行数再涨，可参照本 ADR 同模式拆分
- 将 pyqtSignal 主体声明约束加进 `docs/agents/domain.md` 的 Mixin 指引