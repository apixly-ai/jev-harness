<a id="context-management-for-jev-decisions"></a>
# Jev 决策的上下文管理

[English](context.md) · 简体中文

每一轮都有独立的部分：目标、共享事实、显式纳入的用户/助手消息、当前观察、
动作与结果历史，以及预算。Jev 接收这些部分，再加上可用工具和参数描述。
它不会隐式继承 AI 宿主的对话。

宿主还会在循环的推理上下文中标记 `decision_stage=tool_selection` 或
`parameter_selection`。工具选择问题针对下一步：即使无法完成整个目标，采集证据或
执行前置动作也可以推动任务。调用方的目标和工具契约必须提供前置条件、预期效果、
优先级及顺序要求；候选的位置不提供这些信息。核心没有内置通用的 UI 表单操作顺序。
不带循环标记的直接 `Engine.decide` 筛选仍保留通用候选选择语义。条件参数选择、授权、
独立验证和退出控制仍遵循各自原有的契约。

一次执行可能增加有用证据，却不改变外部观察。在这种情况下，通过 `result_context`
纳入的非 None 安全摘要会记入历史，并能推动下一次决策。原始结果仍可在本地的
`ctx.results` 和日志中获取，但若未纳入上下文，就无法推动观察未变化的状态。
纳入上下文不等于任务完成；独立验证器仍必须通过。

在一次运行内，观察、动作 ID 和实际绑定参数组成的元组标识一次调用。重复调用会在
执行前返回 `blocked/repeated_action_state`。即使摘要相同，不同的绑定对象仍可以提供
不同证据。指纹用于阻止重复执行，不是结果缓存。这不保证跨运行幂等性，也不保证
恰好执行一次。

不支持在固定观察下重复轮询同一次调用。请在可信工具内部实现轮询，并设定明确的
超时和尝试次数上限；或者暴露有实际意义的观察进展。仅仅增加历史记录并不允许再次
进行相同调用。参见[合成离线 A/B](../reports/evidence-progress-ab.json)；这些检查
不能证明真实模型调用成功，也不能证明普遍的性能提升。

默认 ContextPolicy 保留最近八个动作已纳入的结果，并为所有更早的动作保留有序台账，
使用 `step:N` 引用证据。完整证据保留在私有 JSONL 日志和 `ctx.results` 中。目标、
约束、事实及已纳入的消息保持完整。这是确定性的上下文投影，不是推断出的摘要或缓存摘要。

参数绑定会向后传递所选候选的引用和描述，不传递私有的绑定值。已提交的动作历史记录
实际选中的参数，而不是原始的整个候选列表。任务作者应把需要持续保留的任务事实放入
共享事实或观察中，也可以在已注册的工具内从 `ctx.results` 提取所需的旧证据。
运行时不会自动判断哪些业务事实可以安全丢弃。

循环共享上下文保留原有的 15,000 JSON 字符预算，恰好达到上限仍准入：只有
`len(json.dumps(context, ensure_ascii=False)) > 15000` 才拒绝，使用默认分隔符。
计数包含序列化 JSON 的语法、空格和转义，统计该序列化文本中的 Unicode 码点，
不是原始字段长度、UTF-8 字节或 token。

`context_projection` 检查上下文策略的投影加剩余步数/时间预算；`tool_selection`
和 `parameter_selection` 再计量加入 host 阶段标记及选择/绑定增量后的共享上下文。
投影本身可准入，加入这些字段后仍可能超限。候选记录文本、选择问题、完整 prompt
及 token/费用预算不在这项计量内。

reason 为 `context_budget_exceeded` 的终态可能包含仅含计量信息的 `context_budget`：
scope `loop_shared_context`、失败阶段、unit `json_characters`、limit 及 observed 长度。
这项元数据没有原始上下文。返回的决策调用遥测记录 `context_characters` 和
`context_character_limit`，保留 `context_bytes` 作为独立的 UTF-8 大小；异常路径
可能缺少这些计量。受影响的超大决策通常在推理前停止并返回复核，不静默截断约束。
此前可能已有调用/效果；用量不确定性、效果不确定性、调用方回退及无结果缓存策略均不变。

直接 `Engine.decide` 不受这项循环上限控制。固定版本上游对完整 analysis spec 的
独立 16,000 字符验证，以及提供方的问题/状态限制仍有效；共享上下文符合预算，
不证明完整请求也符合限制。消息必须是显式纳入的 user/assistant 对象，并带有文本内容；
系统策略应写入明确的目标和可信程序。[离线 A/B](../reports/context-budget-ab.json)
检查合成准入/计量，真实模型、网络或 UI 调用为零。新增元数据增加终态字节，
不能证明语义质量、提速或费用收益。

请求规划另有接管信息：可选 `telemetry.planning`（loop 中为
`telemetry.calls[].planning`）标识原生空计划，scope 为 `current_selection`、phase
为 `request_planning`，并标记 `inference_dispatched: false`。类型化的收窄/缺上下文
原因仍区分，未知状态使用通用规划复核码。已有的已知零用量只适用于这次选择，不代表
此前 loop 调用/效果或未知用量。应修正候选/描述或必需字段，并保留目标与安全约束，
不盲目重试。不改变 fit 规则、prompt 或上限；通用完整 spec 验证异常和已派发的
HTTP413 保留已有处理。见[规划契约](agent-contract.zh-CN.md#request-planning-handoff)
与[离线 A/B](../reports/planning-diagnostics-ab.json)；它们不能证明语义质量、提速或降费。

传输遥测另有单位和范围。已有 telemetry.requests 与逐次调用的 transport 证据不变；
原生 Choice 计逻辑打包请求。可选 telemetry.owned_transport 从 Session 起点到终态
finish、client close 前，记录本次拥有的 provider client 的 SDK 尝试及 HTTP client
对象创建/复用差值；返回数据包和日志使用同一快照。不可靠差值为 null，元数据缺省
是未知，不是零。SDK 尝试包含重试，可能在编码失败前计数而没有进入 HTTP transport，
不证明服务端收到、推理、计费、TCP 连接或其他工具流量。未知 token 用量仍未知，
上下文准入/执行/重试规则不变。见
[计数契约](agent-contract.zh-CN.md#transport-counters-owned-by-the-run) 与
[A/B 范围](../reports/transport-counters-ab.json)。

私有日志使用独占创建、POSIX 模式 0600、JSONL 追加，以及 flush/fsync；绝不会覆盖
已有路径。日志包含原始观察、实际参数和结果，未经审阅不要公开。CLI 终态输出不含
原始证据；可信脚本也必须避免打印自己的原始数据。

这一设计借鉴了 pi 的显式代理状态和消息投影、Anthropic 上下文工程指南中的轻量引用
与渐进披露，以及 MellowHarness 将结果写入事件历史的方式。它不声称具备这些项目的
完整功能集。参见[架构参考](architecture.md)。
