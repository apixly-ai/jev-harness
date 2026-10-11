# Jev Harness 使用案例

Jev Harness 让 AI 定义可复用工具和目标，再把探索交给 Jev。任务开始时，路线、相关来源
和后续参数可以未知。AI 编写工具、观察、完成与资源契约；Jev 决定下一步工具与参数、
是否继续以及何时停止。程序负责采集、执行和独立验证结果。

[历史演示](https://apixly-ai.github.io/jev-harness/zh/#browser-evidence) ·
[English](use-cases.md) · [任务协议](agent-contract.zh-CN.md)

以下三个案例均为**设计方案，验收待完成**，不是已完成的运行或开箱命令。工具名是任务
作者注册的接口示例。候选列表每步根据观察和准入结果刷新，不要求 AI 预列完整路线，
也不要求编写下一步 router。

<a id="browser-research-through-an-unknown-multi-page-route"></a>
## 浏览器：沿未知多页路线调研资料

**设计方案，验收待完成。**只给入口 URL 和目标，例如：“找出三个满足给定约束的
自托管工具，保存带可核对来源的比较结果。”链接、章节、筛选项
和依赖在浏览时逐步发现。Jev 决定继续探索来源、阅读细节、比较证据还是保存资料包。

| 契约 | 任务定义 |
| --- | --- |
| 输入 | 入口 URL、目标、工具要求、允许来源及时间/步骤预算 |
| 可复用工具 | discover、open、read、compare、collect_evidence、save_dossier |
| 动态参数 | 新观察到的链接、章节、来源对和证据引用；子候选依赖选定来源/控件 |
| 观察 | 当前页面、已发现的待探索项、准入证据和未解决前提 |
| 完成 | 三个不同工具，每项给定约束均由采集来源支持；已保存比较的引用与来源材料一致，缺少支持时保留未解决状态 |

例如，阅读一个来源后才发现启动时未知的前提，打开其引用后又出现新的参数域。
工具 provider 提供当前可用候选和前置条件，不决定下一条分支。同一套工具应适用于
不同布局与来源路径。

验收设计使用**同一脚本**面对三个未知门户变体：

1. 通过一组来源发现适用工具的成功路线。
2. 链接变化、阅读页面后才发现新前提的另一条成功路线，需要不同的探索轨迹。
3. 缺少来源、无法建立所需证据的变体，必须保留已收集证据和未解决终态。

任务及 provider 不得读取 fixture 答案或隐藏路线。独立验收器另行核对来源与已保存
产物。后续真实 Jev 与无头 Camofox 验收应保留新发现的候选集、选定工具参数、不同
路线长度、失败分支及真实模型/用量证据。空候选域或证据超限导致的停止仍须可见，
这个设计不假设自动恢复。目前尚未记录此案例的真实探索结果。

<a id="repository-investigate-a-failure-through-read-only-tools"></a>
## 仓库：使用只读工具探索故障原因

**设计方案，验收待完成。**给定仓库入口和测试或 CI 失败记录，定位相关执行路径，
保存带可检查来源证据的解释。相关文件、符号和假设在运行中发现。

| 契约 | 任务定义 |
| --- | --- |
| 输入 | 仓库范围、已有失败记录、调查目标及资源预算 |
| 可复用工具 | 搜索代码、读取文件/符号、查看已有测试/日志产物、比较证据、保存诊断 |
| 动态参数 | 前序读取发现的路径、符号、行窗口和证据引用 |
| 完成 | 独立核对代码版本/引用，已保存诊断由失败证据支持；未确认结论保留为待复核 |

工具读取代码与已有产物，不修改仓库，也不执行其程序；诊断保存在源码树之外的调用方
输出位置。Jev 选择下一步查看什么，任务作者不提供逐文件路线。精确路径过滤与提取
留在代码中。

<a id="controlled-api-diagnose-an-incomplete-task"></a>
## 受控 API：诊断尚未完成的任务

**设计方案，验收待完成。**从授权测试服务入口出发，判断哪个前提或状态转换阻止
任务完成，保存有证据的诊断。资源链接、schema、事件分页和依赖通过响应逐步获知。

| 契约 | 任务定义 |
| --- | --- |
| 输入 | 授权服务入口、任务目标、只读范围及资源预算 |
| 可复用工具 | 发现资源、读取状态/schema/事件、比较观察、保存诊断 |
| 动态参数 | 响应中发现的资源 ID、schema 引用及分页 cursor；子候选依赖选定资源 |
| 完成 | 独立核对服务状态/事件，已保存诊断关联到这些观察 |

Jev 选择请求哪些证据，以及何时证据足够。程序校验只读操作，只绑定已有资源。
缺证据时保留未解决结果；此案例不修复或修改服务。

<a id="candidate-generation-and-exploration"></a>
## 候选生成与探索

当前原生 loop 选择候选引用，没有内置自由文本生成器。查询、文章或新的候选结构
可以由已注册可信 generator 或主 AI 产生；输出经过校验后再进入候选池，由 Jev
决定使用哪个工具和候选。生成文本不能直接成为可执行代码、命令或 selector。
主 AI 编写或扩展契约，不代替 Jev 路由每一步。

<a id="historical-connection-evidence"></a>
## 历史接通证据

早期表单与 Counter 证明工具选择、绑定和执行曾接通。它们保留原有范围和复现方式，
不证明上面三个开放路线设计已完成。

<a id="browser-prepare-and-verify-a-local-travel-draft"></a>
### 浏览器：准备并核对本地旅行草稿

**目标：**为 Mira 准备目的地为 London、启用灵活日期的草稿。程序负责页面、允许的来源、
输入值和授权策略。浏览器适配器把观察到的控件作为候选，不向模型开放任意 selector、
脚本或由模型生成的表单值。

| 契约 | 程序提供或独立观察的值 |
| --- | --- |
| 输入 | 旅客 Mira、目的地 London、启用灵活日期 |
| 候选 | 观察到的控件与下拉选项；程序提供的具名文本值 |
| 操作 | 填写旅客、选择目的地、勾选灵活日期、准备草稿 |
| 完成 | 唯一观察到的控件值，以及最终文字 `Draft ready: Mira \| London \| flexible=true` |
| 范围 | 本地合成夹具，不创建真实预订或发送消息 |

<figure><video controls muted playsinline preload="none" poster="../web/media/browser-poster.zh-CN.webp"><source src="../web/media/browser-demo.zh-CN.mp4" type="video/mp4"></video><figcaption>使用当前界面截图回放原始夹具步骤。这是无新增推理调用的截图回放，不是新录制的 Jev 推理运行。</figcaption></figure>

历史 **v0.1.0** 验收使用真实 Jev 与无头 Camofox，以 **四次工具执行**完成该夹具。
早期复核结果和授权门槛结果仍保存在[验收账本](../reports/README.zh-CN.md)与
[机器可读证据](../reports/acceptance.json)中。小型夹具成功不证明开放网页或生产任务的普遍成功。

[未修改的原始夹具](../examples/fixtures/form.html)与
[素材生成脚本](../scripts/generate_showcase.py)可以复现展示。在仓库 checkout 中，需要
已运行的具名无头 Camofox 服务、ffmpeg 和 cwebp：

```sh
python scripts/generate_showcase.py
```

素材脚本使用精确程序操作并核对最终控件和文字，不调用模型。
[来源清单](../web/media/showcase.json)记录夹具摘要、媒体摘要和验证字段。
真实任务接口及调用方授权要求见[浏览器适配器](adapters.zh-CN.md)。

<a id="python-select-a-tool-and-bind-an-amount"></a>
### Python：选择工具并绑定递增数量

这个 Counter 是历史接通示例。精确算术通常应由代码处理，小任务用于说明参数接口，
不是开放路线调研。

**目标：**将观察到的计数器从零推进到程序提供的目标三，且不超过目标。任务描述递增工具，
从当前状态提供合法数量。示例序列为 `0 → 1 → 3`；实际步骤取决于该次决策运行。

| 契约 | 程序负责的值 |
| --- | --- |
| 输入 | 当前值与目标 `3` |
| 候选 | 递增数量 `1` 或 `2`，排除会超过目标的值 |
| 执行 | 注册 Python 工具修改实际状态 |
| 完成 | 独立观察值等于输入目标 |

先按[准确的 Git 安装方式](agent-contract.zh-CN.md#install-and-run-your-first-task)准备环境，再使用可运行模板。
前三条命令不调用模型；最后一条付费，需要在环境中提供 `TYPESAFE_API_KEY` 或
`TYPESAFE_API_KEY_FILE`。

```sh
jev-harness spec
jev-harness init-task task.py
jev-harness check-task task.py
jev-harness run task.py --goal 'Reach target without overshooting' --inputs '{"target":3}'
```

生成任务的历史真实验收与小型通用/条件化提示 A/B 见[验收账本](../reports/README.zh-CN.md)。
主页计数器图是机制示意，不是推理录屏。语法检查通过不证明运行时有效，可信 Python 导入
仍可能产生效果。

<a id="runtime-continue-from-evidence-and-stop-repeated-effects"></a>
### 运行时：利用证据继续，并阻断重复效果

**目标：**准入的工具结果提供新证据时继续判断；在相同决策状态下重复相同动作时，于执行前阻断。

| 契约 | 程序提供的值或验证条件 |
| --- | --- |
| 上下文 | 当前观察、准入结果摘要与动作账本 |
| 候选 | 注册工具及程序提供的参数候选 |
| 继续 | 有用的 `result_context` 摘要可推进下一轮决策 |
| 完成 | 独立验证器通过；模型声明完成不足以建立成功 |
| 重复 | 相同观察、动作 ID 和实际参数返回 `blocked/repeated_action_state` |

[离线证据进展报告](../reports/evidence-progress-ab.json)使用固定合成决策。
预期结果既包括完成，也包括阻断和配置拒绝。它验证这些契约行为，不证明真实语义质量，
也不证明普遍提速或降费。在完整 checkout 中安装开发依赖后，可复现：

```sh
python benchmarks/progress.py --output local-results/my-progress-ab.json
```

未经准入的原始工具结果不能推进未变化的观察。不支持在固定观察下反复轮询相同调用；
工具应自行限制轮询，或提供有意义的进展。运行时不提供跨运行恢复或业务效果的 exactly-once
保证。扩展这些案例前，先阅读[上下文管理](context.zh-CN.md)与
[任务协议](agent-contract.zh-CN.md)。

<a id="choosing-a-suitable-task"></a>
## 如何选择合适的任务

适合 Harness 的任务有可复用工具表达有用的下一步，观察与候选域可随任务演进，并有
独立完成检查。限制资源与可执行接口，探索路线可以保持未知。精确确定性工作留在代码中；
主 AI 负责工具/任务编写与自由生成，Jev 负责循环中的工具/参数决策。Jev Filter 提供
推理与平台依赖。

新设计尚未证明任务成功、提速或费用优势。历史浏览器证据保留本地夹具范围，原生
桌面完成仍未验证。定义自身任务的完成和接管条件时，应阅读任务与上下文契约。

[常见问题](faq.zh-CN.md) · [架构](architecture.zh-CN.md) ·
[验收证据](../reports/README.zh-CN.md)
