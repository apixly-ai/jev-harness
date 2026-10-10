# Jev Harness

[English](README.md) · [文档](https://apixly-ai.github.io/jev-harness/) · [AI 接口](docs/agent-contract.md) · [验收证据](reports/README.md)

**编写任务，注册工具，让 Jev 选择下一次调用和参数。**

这是面向 AI 编写有界任务脚本的 Python 运行时。每轮提供目标、准入对话、现场、执行
历史和工具契约，Jev 选择工具与参数候选，程序执行并独立验证完成。Apixly 独立社区
项目，非 TypeSafe AI 官方产品。早期 0.1.4，不承诺通用任务成功或普遍降低费用。

发行名 **apixly-jev-harness**，Python 命名空间 `apixly_jev_harness`，明确 CLI 别名
`apixly-jev-harness`。使用本仓库的准确 Git 安装 URL；PyPI 的 jev-harness 属于其他项目。

## AI 从接口开始

需要 Python 3.10+ 和 Git。底层依赖固定为 GitHub 的 Jev Filter 0.4.1，安装不调用模型。

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@v0.1.4'
jev-harness spec
jev-harness init-task task.py
jev-harness check-task task.py
# 付费：在环境中配置 TYPESAFE_API_KEY 或 TYPESAFE_API_KEY_FILE。
jev-harness run task.py --goal '达到指定目标' --inputs '{"target":3}'
```

仅在开发时将 `@v0.1.4` 换成 `@main`。

check-task 以 UTF-8 读取、解析并编译 Python，要求顶层显式向 workflow 赋值；
单独的 workflow: object 注解不绑定它。不执行待检脚本、不加载其模块、不导入其依赖，
也不调用回调。通过不证明运行时有效，或兼容其他 Python 版本及警告策略。
见[静态检查契约](docs/agent-contract.md#static-task-checking) 与
[离线 A/B](reports/static-check-ab.json)，不执行待检脚本，无模型或真实 UI 调用。
run 执行可信 Python，不是沙箱。只有 done 退出码 0，退出码 2 仍返回终态 JSON，
不确定效果不自动重试。

## 工具和参数语义

```python
from apixly_jev_harness import Parameter, Task

state = {"value": 0}
workflow = Task(
    observe=lambda ctx: {"value": state["value"], "target": ctx.inputs["target"]},
    verify=lambda ctx, seen: seen["value"] == seen["target"],
)

@workflow.tool("向目标前进且不超过目标", parameters={
    "amount": Parameter("下一次递增的数量", lambda ctx, seen:
                        [n for n in (1, 2) if seen["value"] + n <= seen["target"]]),
}, result_context=lambda result: result)
def increment(amount):
    state["value"] += amount
    return {"value": state["value"]}
```

候选可静态声明或从现场生成。depends_on 让子参数在父参数选定后再构造候选；
Option(id, description, value) 分离模型可见语义与实际值。只有一个候选时直接绑定，
其余由 Jev 选择，不凭空生成参数。

工具选择针对**下一步**。取证或满足前置条件可以推进任务，不要求一次调用完成总目标。
由调用方在目标和契约中描述每个工具的前置条件、预期效果，以及适用的退出或优先级规则。
核心没有通用 UI 表单次序规则；候选列表的位置不构成优先级。Host 提供
decision_stage=tool_selection 或 parameter_selection 区分 loop 判断。
直接使用 Engine.decide 筛选候选且不带这个 loop 标识时，保留一般候选选择语义。
参数条件化、授权、独立验证和退出检查保持不变。

## 两种原生接口

- Jev-native：原生 Choice 概率、参数依赖解析、严格引用绑定、弃权与独立完成验证。
- AI-native：机器可读 spec、可运行模板、离线语法检查、Python 接口与随包提供的
  [agent skill](skills/jev-harness/SKILL.md)，不偷偷安装 hook 或拦截全部工具调用。

[上下文管理](docs/context.md) 保留目标、事实、对话、动作账本、近期准入结果与较早
证据引用。原文留在私有日志，预算溢出返回复核，不静默丢失约束。

准入的工具结果摘要可以在观察不变时推进下一轮判断。未经 result_context 准入的
原始结果不能推进这种状态。同一次运行中，相同观察、动作 ID 和实际绑定参数最多
执行一次；重复调用在执行前返回 blocked/repeated_action_state。
不支持观察固定时反复轮询相同调用；应在有界工具内部处理轮询，或暴露有意义的现场进度。

推理未能确定选择时，可能返回由 host 生成的 diagnostic，标明 tool_selection 或
parameter_selection，后者附注册工具/参数标识，以及白名单 reason_codes 和
automatic_retry: false。telemetry.calls 的每次推理记录也带阶段及适用的标识。
[契约](docs/agent-contract.md#decision-diagnostics) 说明原因码与主 AI 接管建议；
诊断不导出异常原文、响应 body 或绑定值。静态候选域、策略和执行错误保留已有终态原因。
诊断不改变执行资格、退出状态或授权。Harness 不自动重复任务调用，固定 SDK 已有的
有界 429/503/529 重试仍保留，因此不承诺只发一次网络请求。

浏览器和桌面是[工具适配器](docs/adapters.md)，不是运行时里的专用业务程序。
Camofox 限定来源并使用新鲜观察目标，桌面依赖 macOS Accessibility/Windows UIA。
调用方授权确切点击动作；身份、业务幂等由脚本负责。

## 验证范围

verify_state 辅助函数必须有非空文本或至少一个控制条件。每个预期控制字段都必须
被观察到，字段缺失不等于观察到了 null。
[证据进展 A/B](reports/evidence-progress-ab.json) 使用合成离线判断，验证结果驱动的
继续执行和重复调用阻断；不代表真实模型验收或普遍性能收益。

[决策诊断 A/B](reports/decision-diagnostics-ab.json) 使用合成离线 HTTP mock，真实模型
调用为零，验证原因码和阶段信息；终态字节增加，未知错误退化为通用码，尚未测量真实
语义恢复成功率。

[工具选择离线 A/B](reports/tool-choice-offline-ab.json) 与
[工具选择真实调用 A/B](reports/tool-choice-live-ab.json) 的范围是六个开发用合成单步
决策 case，分别使用正序和反序候选。Probe 在 intent 前终止，不能证明完整任务、浏览器
或桌面完成。测量结果和用量以报告为准，未证明普遍质量或费用收益。

真实 Jev/Camofox 合成表单以四次工具执行达到独立校验终态，早期复核失败保留。
桌面真实验收尚未证明：本机锁屏阻止了访问，离线测试不能替代。见[完整证据](reports/README.md)。

无结果缓存，独立推理并发最多 30。同步预算在回调之间检查，工具需自限 I/O。
执行前写 intent，未知用量不计零，不提供跨运行恢复或 exactly-once 保证。

## 开发

```sh
pip install -e '.[dev]'
ruff check src tests benchmarks scripts
pytest --cov=apixly_jev_harness
python -m build
python scripts/check_public.py
```

见[架构与参考](docs/architecture.md)。真实测试需 opt-in、显式测试凭证及合成/允许输入；
保留负面结果，区分 mock、真实测试与生产证据。
