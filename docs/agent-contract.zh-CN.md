<a id="the-ai-native-task-contract"></a>
# 面向 AI 的任务契约

[English](agent-contract.md) · 简体中文

本产品是可复用的任务运行时，不是应用专用案例库。代理只需学习一个接口，
并用一个简短脚本提供自己的业务工具。
目标可以开放，路线可以未知；脚本提供能力、新现场候选域和独立检查，不预写完整
下一步序列。边界针对允许的效果、作用范围和资源。见[开放目标](open-goals.zh-CN.md)。

发行包：**apixly-jev-harness**。Python 包：`apixly_jev_harness`。CLI 别名：
`apixly-jev-harness` 和 `jev-harness`。请从下方准确的仓库 URL 安装；
PyPI 上已有的 jev-harness 包是另一个项目。

<a id="install-and-run-your-first-task"></a>
## 安装并运行第一个任务

需要 Python 3.10+ 和 Git。安装过程不会调用模型，但下载包仍需要网络。
固定到 v0.3.0 可以复现这一发布版本；进行持续开发时使用 `@main`。

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@v0.3.0'
jev-harness quickstart
jev-harness init-task task.py --toolkit workspace
jev-harness check-task task.py
# 付费：使用调用方配置的 TYPESAFE_API_KEY 或 TYPESAFE_API_KEY_FILE。
jev-harness run task.py --goal 'Investigate source evidence and save categorized quotes' --inputs '{"root":"permitted-corpus","queries":["relevant_identifier"],"markers":{"implementation":"<source marker>"},"output":"local-results/report.json"}'
```

凭据保存在宿主密钥机制中，不写入任务代码或 CLI 值。Workspace 模板复用来源/证据
工具，输入允许的 root、引用类别/marker 和新输出路径。Marker 检查演示调用方
verifier，不是完整业务验证。检查 status/complete/archive/telemetry 和真实保存产物。
[工具包](toolkits.zh-CN.md)另支持 HTTP 和 Camofox 渲染来源。

<a id="adoption-sequence"></a>
## 接入步骤

1. 阅读 `jev-harness spec`（离线 JSON）。
2. 定义目标、范围、纳入的事实/消息，以及可观察的成功条件。
3. 通过 jev-harness init-task task.py --toolkit workspace 生成脚本，或在 TaskScript(build)
   中组合可复用包；只在任务需要时注册额外工具。
4. 提供运行时范围和引用判定条件；自定义参数使用
   Parameter(description, choices, depends_on=..., selection=...)。
5. 使用合成输入测试回调行为；`check-task` 只用于静态检查。
6. 发起一次 `run` 调用；即使退出码是 2，也要解析终态数据包。
7. 由主代理补齐尚未解决的上下文，或核对执行结果不明确的情况。

路线未知且需要语义分支的目标适合使用循环。精确计算和固定步骤留在代码中；开放式写作
交给主代理或显式的可信生成工具。工具选择决策不构成执行证明，也不构成授权。

<a id="toolkit-and-mcp-interface"></a>
## 工具包与 MCP 接口

EvidenceStore 在进程中保留采集文本和出处。WorkspaceTools/WebTools 注册普通 Task
工具，执行时刷新来源/参数域，提供简洁稳定观察。EvidenceTask 增加按需段落读取、
可用引用类别、依赖段落选择和已保存报告检查。
[28 行示例](toolkits.zh-CN.md#start-with-a-thin-script)从运行时 inputs 获取范围、marker
和输出；业务谓词保留在调用方 record_checks/verify 中，不写下一步 router 或 fixture 答案。

TaskScript(build) 根据已校验的 ctx.inputs 构建一次注册任务，这是配置复用，不是
推理或采集结果缓存。来源/记录观察保留最后八个摘要和有界 last_read；真实产物匹配
当前记录后，verifier 获取全部 records。artifact_receipt() 提供 path/exists/
matches_records/record_count/sha256/sources。采集文本和 session 不自动跨进程续接。

stdio MCP 使用 python -m apixly_jev_harness.mcp task.py --goal ... --inputs ...，可加
--context、--max-steps、--timeout、--archive、--model（带版本号的 Jev ID，默认
jev-1.13.0）。observe 返回当前目标、工具、参数引用、
state_ref 及委托/产物详情。广告的 arguments/operate 必须带这个 state_ref；先给
arguments 父 option ID，再选依赖子 ID。operate 接受已提供 ID，不接受任意绑定值。
一个 session 内顺序操作。既有 Python 方法的 state_ref 参数保持可选兼容，MCP 客户端必传。

开始时选择直接 operate 或 Jev run_task。直接执行后或尝试委托后拒绝切换路线。
Python 使用 session.delegate()，旧 MCP incoming alias 保留但不广告。run_task
使用同一目标、inputs、注册能力和独立检查。直接模式的主模型用量不在 Jev 遥测内；
路径发现/采用与任务成功是不同证据。见
[工具包指南](toolkits.zh-CN.md)和[验收账本](../reports/README.zh-CN.md)。

selection="explore" 用于值得探索的来源/规划候选，不要求未知目的地已经证明目标。
EvidenceTask 工具选择和 explore 参数使用开发校准的 0.30 top probability/0 margin，
默认 match 保留 0.55/0.10；其他检查和执行权限不变。小范围开发选择不证明质量、
普遍提速或费用改善。

<a id="cli-argument-parsing"></a>
## CLI 参数解析

当 argparse 在任意命令解析器中报告错误时，CLI 只打印下方固定数据包，并以退出码 2
退出；直接调用 `main` 时会打印该数据包并返回 2：

```json
{
  "status": "failed",
  "complete": false,
  "phase": "arguments",
  "code": "invalid_command_arguments",
  "script_loaded": false,
  "model_calls": 0
}
```

这一过程发生在命令分发或任务模块加载之前，不输出原始错误消息、参数值、用法文本
或 `error_type`。详细的解析器诊断会丢失。Argparse 可能暂时构造包含 argv 值的消息；
抑制输出不会清除进程内存中的 argv 或临时字符串。这一契约支持常规 CLI 字符串参数，
不支持把任意 Python 对象作为 argv 传入。

有效的 `--help` 保留面向人的文本、`SystemExit(0)` 和原有解析器优先顺序。Help 可能
在后续未知参数检查之前退出，所以并非所有包含未知 token 的调用都会产生错误数据包。
Help 会显示程序名（`prog`），这一内容不在原始消息抑制范围内。
有效的长选项缩写行为保持不变。

遇到 `arguments` 失败时，应查看 `spec`/help 并修正命令；这不属于工具执行失败。
解析成功后，格式错误的 JSON 或无效的 `run` 配置仍使用 phase `configuration`
和 code `invalid_run_configuration`。可信加载完成后才会出现运行时任务状态；
静默中断的任务仍不返回数据包，需要核对效果和用量。SDK/`Engine.run` 保持不变。
[cli-arguments A/B](../reports/cli-arguments-ab.json) 是离线的合成解析器检查，
没有真实模型、网络或 UI 调用；它不能证明任务成功。

<a id="static-task-checking"></a>
## 静态任务检查

`check-task` 读取 UTF-8 源码，解析 AST 并编译，但不执行。它绝不会执行被检查的
脚本、加载其模块、导入其依赖或调用回调。静态导出检查接受显式的顶层 `workflow`
赋值（带值的 `Assign` 或 `AnnAssign`）。例如，`workflow = expression` 和
`workflow: object = expression` 声明了赋值；单独的 `workflow: object` 不绑定值。
检查不会推断动态或条件导出。

通过检查的结果仍使用 JSON code `syntax_and_export_ok`。它只表示当前 Python
解释器能编译该源码，并且 AST 声明了上述赋值。它不能证明 `workflow` 的类型、
导入成功、执行路径可达、工具签名、候选提供函数或实际效果。其他 Python 版本和
警告策略可能有所不同。

无法编译的源码返回 `invalid_python` 并附带 `line`；非 UTF-8 源码返回
`source_not_utf8`。若有解析/编译警告，只通过
`source_warnings: [{"code": "python_source_warning", "line": N}]` 暴露；
警告文本和源码片段不会输出，也不会打印到 stderr。这些诊断不执行任务，也不对任务
做语义验证。

[static-check A/B](../reports/static-check-ab.json) 使用固定的离线脚本样本，
不执行任何被检查的脚本，模型或真实 UI 调用均为零。它测试静态准入和安全诊断，
不测试运行时任务成功。

<a id="run-configuration-preflight"></a>
## 运行配置预检

在创建、注册或加载可信任务模块之前，CLI `run` 会解析 inputs/context/messages JSON，
并使用引擎共享的辅助函数验证配置：

- 目标非空，`max_steps` 为正整数，超时为正且有限。
- CLI inputs/context 必须是 JSON 对象，messages 必须是 user/assistant 消息组成的
  JSON 列表，消息 content 为字符串；显式 `null` 会被拒绝。
- `required_context` 路径语法有效。Goal、inputs、context 和 messages 必须能序列化为
  有限 JSON 并编码为 UTF-8；孤立的代理码位会被拒绝。

在 Python API 中，只有省略字段或传入 `None` 才会采用默认的 `{}` inputs/context
或 `[]` messages。其他假值参数必须具有正确类型；`[]`/`False` inputs 和
`{}`/`False` messages 不会被静默替换。这种 API 默认值规则不同于 CLI JSON `null`。
required-context 可迭代对象只规范化一次，并保留供运行时使用。路径有效但对应事实
缺失时，仍产生运行时 `needs_context`，与配置无效相区分。

无效的 CLI 配置会返回如下数据包：

```json
{
  "status": "failed",
  "complete": false,
  "phase": "configuration",
  "code": "invalid_run_configuration",
  "script_loaded": false,
  "model_calls": 0,
  "error_type": "ValueError"
}
```

数据包不包含原始值和异常文本。配置有效时会继续导入可信 Python，包括其所有顶层
副作用。预检不检查 workflow 签名、依赖、归档是否可用、凭据或业务条件，也不保证
后续没有副作用或任务能够成功。它不是沙箱；独立的 `check-task` 命令仍只检查编译和导出。

[run-preflight A/B](../reports/run-preflight-ab.json) 使用离线合成的导入标记及
不调用模型的 workflow，没有实际 API 或 UI 调用。它测试加载之前的配置准入，
不测试真实模型或任务性能。

<a id="cli-task-output"></a>
## CLI 任务输出

配置准入后，CLI `run` 在可信模块创建、注册、导入及循环执行期间替换 Python
stdout/stderr。写入这些重定向流的内容只计数并丢弃，不保留或存储其内容。
恢复原始流之后才打印最终终态 JSON。Python SDK 的 `Engine.run` 保持不变。
这一输出策略只适用于 `run`；参数错误数据包适用于所有命令解析器。配置预检、
有效 help，以及成功的 `spec`、`skill`、`check-task` 和 `init-task` 保留现有契约。

如果丢弃了非零输出，返回的数据包会有可选的 `task_output`：

```json
{
  "task_output": {
    "policy": "discard",
    "scope": "python_streams",
    "stdout": {"characters": 1, "binary_bytes": 0},
    "stderr": {"characters": 0, "binary_bytes": 0}
  }
}
```

以上计数只演示数据结构，不是验收测量结果。`characters` 计数传给文本写入的 Unicode
码点，不进行编码；`binary_bytes` 计数写入 `.buffer` 的 `memoryview.nbytes`。
这两个量使用不同单位，不能合并成 UTF-8 字节总数。流报告 `encoding='utf-8'`，
但不会对文本进行编码。它们是非 TTY 流，打开时 flush 不执行任何操作，并且不支持
`fileno()`。只有空写入时不会添加这项元数据。计数不代表工具成功，也无法重建
丢弃的 print、警告或调试文本；请使用结构化工具返回值和纳入的 `result_context`
作为证据。

重定向作用于整个进程，不提供任务/线程隔离；不要在同一个 Python 进程内运行时间
重叠的 CLI 任务。重定向有效期间，计数可能包含其他线程的写入，后续输出也可能逸出。
持有旧流的日志处理器、直接写入原始流或 OS 文件描述符、子进程，以及显式文件日志
都不在这一范围内。这不是沙箱，也不保证每个输出通道都是私有的，或任意可信脚本
总能输出可解析的终态数据包。

普通异常状态仍保持类型化；在已进入的工具执行期间发生的错误仍保留
`execution_uncertain`，且不会自动重试。在受保护的 CLI 任务路径中，
`SystemExit`/`KeyboardInterrupt` 会恢复流，并变成静默的非零退出，
抑制原始中断参数和 traceback：

- `KeyboardInterrupt` 变成退出码 130。
- `SystemExit` 保留 1 到 255 范围内的精确整数退出码。零、`None`、字符串、
  范围外整数和其他值都变成退出码 1。

直接调用 CLI `main` 时也适用：它抛出 `SystemExit(code)`，抑制原始异常上下文，
而不是返回数据包。这些退出没有终态 JSON 或输出计数元数据。它们既不能证明用量
完整，也不能证明没有副作用；新一轮运行之前必须核对。有效 help 的退出行为保持不变，
SDK/`Engine.run` 也保留原有中断行为。[task-output A/B](../reports/task-output-ab.json)
检查离线合成的流写入和终态解析，没有真实模型、网络或 UI 调用；它不能证明任务成功
或进程输出完全隔离。

<a id="next-step-tool-selection"></a>
## 下一步的工具选择

循环会让 Jev 从提供的工具中选择一个工具或退出，针对的是**下一步**，并以完整目标
作为上下文。即使一次调用不能完成目标，采集证据或执行前置动作也可能是合适的选择。
应说明每个工具的前置条件和预期效果，并在调用方的目标及工具契约中提供任务顺序、
优先级和退出条件。候选列表中的位置不代表优先级。核心不规定通用的 UI 表单操作
顺序；业务顺序由任务作者定义。

宿主会把 `decision_stage=tool_selection` 或 `parameter_selection` 加入循环决策
上下文。该标记限定问题范围，不提供权限或成功证明。不带循环标记的直接
`Engine.decide` 筛选仍保留通用候选选择语义。参数仍根据已选工具的下一次调用来
选择值。授权、独立完成验证及类型化退出检查保持不变。

工具选择的[离线](../reports/tool-choice-offline-ab.json)和
[在线](../reports/tool-choice-live-ab.json) A/B 报告针对六个开发用合成单次决策案例，
分别使用正常及反转的候选顺序。探针在记录执行意图之前停止。这一范围不能证明完整
任务、浏览器或桌面任务完成，也不能证明普遍的质量/成本收益；测量结果和用量见报告。

<a id="parameter-protocol"></a>
## 参数协议

每个参数都有语义描述，以及由 list/tuple 提供的候选，或只读提供函数
`(ctx, observation)` / `(ctx, observation, bound_arguments)`。候选是 JSON 值
或 `Option(id, description, value)`。字面值会转为描述；Options 将模型可见的安全
标签与实际值分开。不要把凭据放进模型可见的标签或观察中。

候选 provider 必须能绑定两个或三个位置参数，不按参数总数判断。允许可选的仅关键字
参数。先取 inspect.signature(provider, follow_wrapped=False)，仍尊重显式 __signature__：

- 入口没有 *args，或至少有三个显式位置槽位时，使用入口签名。同步 bridge 即使其
  __wrapped__ 委托只声明两个参数，也可接收已绑定父参数；反向的两槽入口仍接收两个。
- 含 *args 且显式位置槽位少于三个时，为兼容性保留默认 advertised 委托签名。
  所选参数数量须同时可绑定 advertised 契约与入口签名。

先尝试三个参数，再尝试两个。入口要求四个参数，或必需仅关键字参数导致两种形式都
无法绑定时，在调用 provider 函数体之前报告 CallbackContractError，code 为
provider_signature_unsupported、callback 为 choices。Partial 和可调用对象的 provider
遵循相同规则。只改变 provider 的参数数量判断，Task.tool 签名检查和回调类型检测不变；
类型检测不新增 __wrapped__ 展开，准入不调用 provider 函数体，仍是同步引擎。
显式签名元数据仍可能有误，带一/
两个命名槽位的复杂 *args 包装器若委托元数据不实，仍可能不支持。应使用明确的两/
三参数入口或准确 __signature__；内省和准入都不证明函数体行为。见
[provider 签名 A/B](../reports/provider-signature-ab.json)的测试范围。

任务注册会保留动态提供函数的 callable 身份，包括其绑定的 client、锁和状态，
同时对静态候选进行深拷贝。每当一个步骤需要提供函数的候选域时，都重新调用该函数；
提供函数的结果没有缓存。

每次采集候选域时，_domain 先检查重复 ID 及原有数量上限，再把完整 option 列表
深拷贝后交给选择。普通 Option 和原始 dict/list 值与 provider 共享来源在等待
选择期间的后续修改隔离，实际绑定值来自这次候选域快照，而不是选择中被修改的来源
引用。默认 staged 与 joint 调用目录保留接口；这是逐次候选域快照，不保证所有后续
绑定步骤复用同一个菜单。

Provider 身份保留，需要候选域时仍重新调用。不增加结果缓存、provider 原子采集、
全局 freshness 或沙箱。Deepcopy 按全部候选值的对象结构增加时间/内存开销，包括
未选值；
不可变字符串可能沿用，序列化 JSON 字节数不表示新增堆内存。
自定义 deepcopy 可失败或执行可信 Python，其行为未获证明。因此未选值的复制失败也可能让先前成功
流程更早 failed/阻塞。既有失败/未知用量处理及执行权限保留，业务 freshness 与身份
仍由调用方工具负责。见[参数快照 A/B](../reports/parameter-snapshots-ab.json)，复制不
带来提速或降费保证。

`depends_on=('customer',)` 仅在选定 customer 之后构造 job 候选域。依赖图必须无环，
并引用已存在的参数。描述参数时，应面向已选工具的下一次调用；不要要求一个值完成
整个任务。精确算术和固定值应在代码中计算；只有一个候选的域不需要推理。每个返回值
都属于实际提供过的候选。模型不能生成工具名、路径、脚本或 selector。v0.1 不提供
任意自由文本参数生成或通用 JSON Schema 验证。工具必须自行验证业务条件。

默认的分阶段绑定先选择工具，再按依赖顺序选择每个参数。只有一个候选的域直接绑定，
不调用推理。这避免了笛卡尔积膨胀。显式 `strategy='joint'` 支持小规模的完整调用
目录，用于受控比较。最多 250 个工具/调用，每个参数最多 253 个候选。
空的子候选域会请求上下文，不会猜测值。

<a id="offered-action-consistency"></a>
## 已提供动作的一致性

低层 Task.bind/Task.execute 防护在查找最近提供的快照之前，要求精确的 Action 实例
及 builtin str ID。id、description、params、irreversible 四个字段复用已有内部类型
比较。布尔/数字替换不匹配，包括嵌套值与字典 key；list/tuple 只匹配同类，支持
builtin None/bool/int/有限 float/str/list/tuple/dict。有限数字 1/1.0（含数字 key）仍
相等。这是已提供字段一致性，不是字节相同或对象身份；不新增公开比较 API，也不
改变全局 Action.__eq__。

不支持的值/子类即使 Action 未修改也不匹配，先前接受的 JSON 兼容 Enum、str/dict/list 子类
可能变为拒绝。应在提供候选前把数据正规化为合适的 builtin 值，不要选择或绑定后
转换 Action；传回已提供/已绑定的 Action。递归比较增加本地遍历开销，比较不调用
自定义相等方法，但可信 deepcopy、JSON 及其他准备过程仍可执行 Python hook。
这不是沙箱或原子采集，也不证明业务身份或外部目标 freshness。

直接调用保留 bind 的 ValueError('action_not_offered') 与 execute 的
ValueError('action_not_bound')。Engine 中 bind 拒绝通常返回 failed；execute 拒绝即使
尚未进入工具函数体，也可能返回 execution_uncertain 及可用的 pending action ID，
因为执行已被标记为开始。拒绝本身不证明零效果。此前效果与未知用量保留，不自动
重试。标准 Engine 传递选定的 Action，不主动改写它。自定义 Workflow 行为、fingerprint、
verify_state、模型选择、授权、缓存及 freshness 规则不变。见
[动作一致性 A/B](../reports/action-identity-ab.json)，范围是合成低层一致性与兼容，
不代表真实模型攻击、普遍错参、AI 语义质量、提速或省费。

<a id="synchronous-callback-contract"></a>
## 同步回调契约

运行时接受声明为同步的回调。Task 的 `observe`、`verify`、`authorize`，工具的
`execute`、`available`、`result_context`，以及 Parameter 的 `choices`，都会拒绝
已知的 coroutine、async-generator 和 generator 函数。同样的检查适用于自定义
Workflow 的 `observe`、`candidates`、`execute`、`verify`、`authorize`、`bind`、
`result_context`，以及 context-policy 的 `build`。同步 generator
`Workflow.candidates` 是例外；它可以 yield 候选动作。

内省能透过 partial 和可调用对象识别已知的延迟执行声明，而不调用其函数体。
回调类型检测只沿 partial 的 `.func` 链检查，不使用 `inspect.unwrap`，
也不跟随 `__wrapped__`；显式同步阻塞包装器会保留。它无法静态证明普通包装器的
返回内容，也不会自动 await coroutine 或 async-generator 的返回结果。
这仍是同步运行时，不是异步引擎或沙箱。注册可以发生在可信脚本导入期间，在更早的
顶层副作用之后；`check-task` 仍只检查解析、编译和导出。

已知的延迟执行回调会报告 `synchronous_callback_required`；无法绑定的候选提供
函数会报告 `provider_signature_unsupported`。CLI/运行时数据包可能包含
`contract_error`，其中有固定 code、回调角色和可选 kind，例如：

```json
{
  "contract_error": {
    "code": "synchronous_callback_required",
    "callback": "execute",
    "kind": "coroutine"
  }
}
```

`callback` 是契约中的角色，不是所提供 callable 的名称。若出现 `kind`，其值为
`coroutine`、`async_generator` 或 `generator`；context-policy 的 `build` 使用
回调角色 `context_policy`。这一诊断不输出异常文本、名称或绑定值。已在执行中的
工具发生错误时仍为 `execution_uncertain`，不会重试。授权及独立验证保留原有要求。

[callback-contract A/B](../reports/callback-contract-ab.json) 检查离线合成的回调
准入和提供函数绑定，使用脚本化决策，真实模型、网络或 UI 调用均为零。
它不能证明普遍的任务成功、速度提升或成本节省。

<a id="context-and-results"></a>
## 上下文与结果

`Context`：goal、inputs、facts、messages、step、results、history。Inputs/绑定值
不会自动发送给 Jev。`result_context(result)` 显式纳入安全的 JSON 摘要；完整结果
仍保留在本地。来源观察/结果是证据，不是指令。

<a id="loop-context-budget"></a>
### 循环上下文预算

循环共享上下文保留原有的 15,000 个序列化 JSON 字符上限，恰好达到上限仍准入。
按 `len(json.dumps(context, ensure_ascii=False))` 和默认分隔符计量，包含 JSON
语法与转义，不是原始文本、UTF-8 字节或 token。先检查上下文投影，再检查工具/参数
选择阶段增加的阶段标记及绑定上下文。候选记录文本、选择问题、完整 prompt 和费用
预算不在这项计量内。

reason 为 `context_budget_exceeded` 的终态可能包含 host 生成、仅含计量信息的
`context_budget`，例如：

```json
{
  "reason": "context_budget_exceeded",
  "context_budget": {
    "scope": "loop_shared_context",
    "stage": "parameter_selection",
    "unit": "json_characters",
    "limit": 15000,
    "observed": 15001
  }
}
```

观测长度仅演示结构。阶段为 `context_projection`、`tool_selection` 或
`parameter_selection`；这项元数据不输出原始上下文。返回的决策调用记录新增
`context_characters` 和 `context_character_limit`，保留已有的 UTF-8
`context_bytes`；异常路径不一定提供这些计量。溢出通常会在调用 Jev 之前停止该次
推理并返回 `needs_review`，不自动截断或缓存。此前的调用/效果和原有不确定性处理
保留；新一轮运行前应检查遥测并核对效果。

直接 `Engine.decide` 不使用这一循环上限，已有的上游完整 spec 及提供方限制仍然
有效。见[上下文管理](context.zh-CN.md)与
[离线上下文预算 A/B](../reports/context-budget-ab.json)。A/B 覆盖合成准入/计量，
没有真实模型、网络或 UI 调用。新增元数据增加终态字节，不能证明语义质量、提速或降费。

当观察没有变化时，新纳入的非 None 摘要可以推动循环。仅有未纳入的原始结果不能
推动该状态。在一次运行内，重复相同观察、动作 ID 和实际绑定参数时，会在执行前
停止，返回 `blocked` 及 reason `repeated_action_state`。即使结果摘要恰好相等，
不同的绑定对象仍属于不同调用。这一防护存储调用指纹，不缓存结果；它不保证跨运行
恰好执行一次。

循环不会在固定观察下轮询相同调用。请把这种轮询放进一个自行限制超时和尝试次数
的工具内，或提供有实际意义的观察进展。不要添加人为计数器来掩饰重复的外部效果。

`observe` 回调和候选提供函数是只读的。`verify` 返回严格的 bool。
`authorize(ctx, action)` 在已有调用方授权的基础上，对准确的不可逆动作返回严格的
True。默认没有授权。执行函数必须有显式、可通过关键字调用的签名；不允许可变参数。
Python 脚本是可信代码，不在沙箱中运行。

`verify_state(text=..., controls=...)` 要求非空文本或至少一个控件条件。每个预期
控件字段都必须出现在观察到的控件中；字段缺失不能证明观察到的值是 `null`。
即使纳入的结果允许继续选择工具，完成任务仍需要独立验证器通过。

Helper 对控件值递归匹配，支持精确的 builtin None、bool、int、有限 float、str、
list、tuple、dict。True/1 与 False/0 不同，包括嵌套值和字典 key；数字 1/1.0 仍
等价，包括数字 key。List/tuple 仅在同类内递归比较，不互相转换；字典 key 按
null/boolean/number/string 类型分类匹配。不支持的值、key 和子类不匹配，值比较
不将完成判断委托给自定义对象的 __eq__。

Helper 的观察根须为精确 builtin dict、所有字段 key 为 builtin str，之后才查找
text/controls；不支持的 root 不匹配。检查控件时，预期记录必须是精确 builtin dict，
字段 key 与 label 都为 builtin str；不合法
记录保留原有 control_check_requires_label_and_expected_fields 配置错误。检查控件时，
观察集合须为 builtin list/tuple，记录为精确 dict 且字段 key 为 builtin str。
格式异常的记录会让 helper 返回 false，不过滤后伪造唯一匹配。这项外层字段规则
不禁止嵌套值中受支持的数字 key。比较避免自定义相等调用，但 helper 构造及周围可信
loop 的 deepcopy/JSON 排序仍可能调用 Python hook，不是沙箱，也不声明不会执行
任意 Python。

预期文本只接受 None/builtin str；其他类型/子类在任何 strip 调用之前，以原有
verification_text_required 配置错误拒绝。这是构造阶段拒绝，不同于不支持的比较值
返回 false。检查文本时，观察值必须是 builtin str；list/dict 包含预期文本并不满足条件。先前
隐式的自定义 matcher/子类支持收窄；需要其他语义或复杂对象时，使用调用方的 verify。
0.1.14 这一改动只改变 verify_state，不改变全局输入准入、自定义验证器、模型选择、授权或候选刷新/
无缓存。初始检查不通过后，可能继续执行工具并增加选择调用，替代错误 done；已有
执行门槛仍有效。[类型验证 A/B](../reports/verification-types-ab.json)针对独立的类型
验证，不代表 AI 语义准确率或真实浏览器/桌面验收，不暗示全矩阵行为一致、提速或降费。

<a id="terminals"></a>
## 终态

`done` 要求独立验证通过。Jev 也有类型化的 complete/blocked/missing-context 控制；
仅由模型判断完成时，状态为 `needs_review`。其他状态为 `needs_context`、
`needs_review`、`needs_confirmation`、`blocked`、`stale`、`max_steps`、
`budget_exceeded`、`execution_uncertain`、`failed`。返回的运行时数据包仅在 done
时使用退出码 0；其他返回的运行时结果使用退出码 2。中断的 CLI 任务以非零退出码
退出，不返回数据包。

执行意图在产生副作用之前持久记录。执行结果不确定时不自动重试。不保证跨运行恢复
或恰好执行一次。业务工具负责身份、幂等性、事务和外部结果核对。运行时间预算使用
协作式检查点；每个回调必须自行限制 I/O 超时。推理没有结果缓存。

在每轮顶部，verified(state) 返回 false 后保留现有 max_steps 检查，再在调用
workflow.candidates（包括 Task 候选 provider）之前重查耗时。该检查发现已达到或超过
超时预算时返回 budget_exceeded，不启动这次候选采集。该验证晚到的 true 仍返回 done；
验证为 false 且已达到步骤上限时，仍在这个超时检查前返回 max_steps。新检查点不会
中断正在运行的回调，也不是每个
回调边界都检查，不构成完整硬截止。此前效果和未知用量保留；上下文、模型选择、
授权、selector 与绑定规则不变。其他验证路径（包括执行后观察不变的处理）保留原有
行为，不新增自动重试。

这会把此位置过预算后的空候选 blocked 或候选抛错 failed 改为 budget_exceeded。
跳过读取后不能再获得那些下游空列表或异常诊断。应检查终态及此前证据，不把它当成
工具失败，也不假定此前没有活动。见
[候选预算 A/B](../reports/candidate-budget-ab.json)，保留这一取舍，不声称普遍提速或省费。

当前执行窗口发生 DecisionStop 时，execution_uncertain 在当前 pending 的已绑定
action_id 存在时携带它。这个窗口覆盖 execute、结果准入、即时 observe 及观察未变时
的 verify。不从历史推断 ID；执行前停止或 pending 已清零后的停止，不会借用旧 ID。
普通异常已携带可用的 pending ID。这个标识用于定位私有日志证据并核对目标状态，
不证明效果成功或执行次数，不是幂等 key，也不授权重跑。这个终态字段不新增绑定参数。
退出行为、授权、重试策略和用量处理均不变，未知用量仍为未知。
见[执行标识 A/B](../reports/execution-identity-ab.json)的接口边界。

<a id="decision-diagnostics"></a>
## 决策诊断

终态数据包可能包含宿主生成的可选 `diagnostic`，用于尚未解决的工具或参数选择调用。
它不改变终态、执行资格或授权。例如：

```json
{
  "status": "needs_review",
  "complete": false,
  "diagnostic": {
    "stage": "parameter_selection",
    "tool_id": "inspect_record",
    "parameter": "record",
    "reason_codes": ["model_review"],
    "automatic_retry": false
  }
}
```

`stage` 是 `tool_selection` 或 `parameter_selection`。参数阶段包含来自已注册绑定
上下文的 `tool_id` 和 `parameter`。`telemetry.calls` 中的每个选择调用条目都带有
相同的 stage 及适用的标识符。只有一个候选的绑定不会产生推理调用。静态候选域、
策略和执行失败继续使用原有终态原因；诊断仅覆盖选择调用。

`reason_codes` 只允许这些稳定 code：

- 提供方：`credentials_missing`、`credentials_invalid`、`credential_file_permissions`、
  `client_closed`、`response_too_large`、`transport_failed_usage_unknown`、
  `response_invalid_usage_unknown`、`retry_exhausted`、`provider_unavailable`，以及
  HTTP 状态码 100–599 对应的 `http_NNN_body_suppressed`。
- 选择：`below_min_top_probability`、`below_min_margin`、`below_min_confidence`、
  `selected_option_not_top`、`model_review`、`no_matching_candidate`、`invalid_selection`、
  `unresolved_selection`、`decision_failed`。
- 请求规划：`request_needs_narrowing`、`request_needs_context`、`request_planning_review`。

诊断绝不输出异常文本、响应正文或绑定参数值。未知错误回退为通用 code；code 是
交接信号，不是对上游根因的诊断。缺失/未知用量仍保持未知。

主代理可以针对凭据 code 修复本地凭据配置，或针对选择 code 检查已纳入的上下文，
收窄有歧义的候选。在提交新任务之前，应查看状态和日志：后续决策失败不会撤销先前
产生的副作用。应核对不确定的执行结果，而不是重试。`automatic_retry: false`
表示 harness 不会自动重复任务调用；固定版本 SDK 原有的有界 429/503/529 重试
保持不变。这不保证只发起一个网络请求，也不保证自动恢复。

[decision-diagnostics A/B](../reports/decision-diagnostics-ab.json) 使用合成的离线
HTTP mock，真实模型调用为零。它检查安全 code 和阶段元数据。额外元数据会增加
终态字节数，未知错误会丢失细节，目前尚未证明真实语义恢复的成功率。

<a id="request-planning-handoff"></a>
## 请求规划接管

固定版本的原生 choice planner 没有生成推理项时，返回的遥测包含 `planning`；
loop 中为 `telemetry.calls[].planning`，直接 choice 为 `telemetry.planning`。例如：

```json
{
  "planning": {
    "scope": "current_selection",
    "phase": "request_planning",
    "inference_dispatched": false,
    "reason_codes": ["request_needs_narrowing"]
  }
}
```

类型化规划判断的 `NEEDS_NARROWING` 对应 `request_needs_narrowing`，`NEEDS_CONTEXT`
对应 `request_needs_context`。未知规划判断转为 `UNAVAILABLE` 与通用
`request_planning_review`，不输出原状态文本，也不猜测原因。空记录列表的原因码为空，
保留现有结果语义；其他选择路径不包含这项元数据。Loop 诊断保留这些白名单原因码
及已有工具/参数阶段，不改变运行时退出状态。

`inference_dispatched: false` 只证明这次选择没有进入原生推理 runner。已有的已知
零用量保留，不证明整个 loop 请求/效果为零或用量完整。此前已花费的调用、效果和
未知用量仍保留在终态证据中。应按阶段检查程序提供的候选/描述或必需上下文/记录字段，
保留目标与安全约束，有意识地修复输入，不盲目重试。

不新增准入上限，也不改变 fit 规则、prompt 或模型选择。这不同于 `model_review`、
提供方失败或通用验证异常。独立的 16,000 字符完整 spec `ValueError` 路径不重新
分类；已派发的 HTTP413 仍保留 `http_413_body_suppressed` 和未知用量。Loop 含上限
的 15,000 JSON 字符预算、授权、验证及不确定性处理均不变。
[规划诊断 A/B](../reports/planning-diagnostics-ab.json) 使用离线合成的规划/派发检查，
没有真实模型、网络或 UI 调用，不能证明语义准确率、提速或费用收益。

<a id="transport-counters-owned-by-the-run"></a>
## 本次运行拥有的传输计数

telemetry.requests 保留原有口径：累加各次决策遥测，原生 Choice 报告逻辑打包请求。
已有逐次调用的 transport 证据保留。可选 telemetry.owned_transport 单独记录本次
拥有的提供方 client 从 Session 起点到终态 finish 的计数，例如：

```json
{
  "owned_transport": {
    "scope": "run_owned_provider_client",
    "snapshot": "terminal_finish",
    "request_attempts": 3,
    "clients_created": 1,
    "client_reuses": 2,
    "counters_complete": true
  }
}
```

计数仅演示结构，不是 A/B 测量值。它们是本次拥有的 Client.stats 中 requests、
clients_created、client_reuses 的差值。一个逻辑请求在重试后可有三次 SDK 尝试，
凭据拒绝时也可能逻辑请求为一而尝试为零。快照取于日志终态写入及 client close 之前，
返回数据包和日志使用同一快照。
spec.transport_counters.snapshot 是实际固定值 terminal_finish，snapshot_timing
另行描述采样顺序；这个机器契约不是 JSON Schema 验证器。

每个计数要求起点和终点是精确的非负整数，终点不低于起点或已见的 Session.run 计数。
缺失、无法读取、bool、负数、字符串或回退的计数都为 null，不推断成零。
只检查这些已观察值，不检测观察间的每一次重置。
counters_complete 只表示三个差值都可用，不证明 token 用量完整。没有活跃的本次
Session 时省略元数据；缺省是未知，不证明尝试为零。

这是 SDK 尝试计数，包含已有重试，不证明 HTTP 已发出、服务端收到、推理发生或计费
完整。JSON 编码失败前也可能已计一次尝试，而没有进入 HTTP transport。Client 计数
是 HTTP client 对象/复用次数，不是 TCP 连接；其他工具流量或 provider client 不在
此范围。模型身份、未知用量、授权、执行、退出状态及重试策略均不变。见
[传输计数 A/B](../reports/transport-counters-ab.json)的测试范围；这些计数不带来价格、
降费或提速保证。

`selection_description(action)` 是可选的同步工具阶段视图。Engine 传入独立 Action 副本，
原始已提供 action 保留执行身份；TaskScript 在缓存任务前完成此回调的同步准入检查。
EvidenceTask 选工具时提供参数契约、候选数量及最多三个 80 字符提示；绑定阶段仍收到
全部最新候选，直接 MCP 检查也保留完整参数域。执行期限结束后仍可分页读取已保存报告；
这不会恢复操作、调用 Jev，也不代表目标完成。
