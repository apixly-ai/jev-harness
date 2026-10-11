# Jev Harness 使用案例

Jev Harness 是 Apixly 的独立 Python 智能体任务运行时。程序提供注册工具、参数候选与完成
条件，Jev 选择下一步工具和候选引用，程序执行并独立验证结果。以下三个案例展示这一契约
的不同环节。

[查看交互演示](https://apixly-ai.github.io/jev-harness/zh/#showcase) ·
[English](use-cases.md) · [任务协议](agent-contract.zh-CN.md)

<a id="browser-prepare-and-verify-a-local-travel-draft"></a>
## 浏览器：准备并核对本地旅行草稿

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
## Python：选择工具并绑定递增数量

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
## 运行时：利用证据继续，并阻断重复效果

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

适合 Harness 的任务能够用注册工具与程序提供候选表达有用的下一步，能够刷新观察，且有独立
成功条件。精确确定性工作留在代码中，开放规划与写作留给主 AI。Jev Filter 负责多条记录的
重复语义筛选；Harness 将它作为有边界执行循环的推理与平台依赖。

浏览器和桌面是通用适配器。原生桌面完成仍未验证，桌面必须解锁并具备所需权限。
不承诺普遍成功、节省模型费用、沙箱隔离或跨运行幂等。

[常见问题](faq.zh-CN.md) · [架构](architecture.zh-CN.md) ·
[验收证据](../reports/README.zh-CN.md)
