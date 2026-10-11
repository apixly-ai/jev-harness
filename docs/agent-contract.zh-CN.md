<a id="the-ai-native-task-contract"></a>
# 面向 AI 的任务契约

[English](agent-contract.md) · 简体中文

本产品是可复用的任务运行时，不是应用专用案例库。代理只需学习一个接口，
并用一个简短脚本提供自己的业务工具。

发行包：**apixly-jev-harness**。Python 包：`apixly_jev_harness`。CLI 别名：
`apixly-jev-harness` 和 `jev-harness`。请从下方准确的仓库 URL 安装；
PyPI 上已有的 jev-harness 包是另一个项目。

<a id="install-and-run-your-first-task"></a>
## 安装并运行第一个任务

需要 Python 3.10+ 和 Git。安装过程不会调用模型，但下载包仍需要网络。
固定到 v0.1.9 可以复现这一发布版本；进行持续开发时使用 `@main`。

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@v0.1.9'
jev-harness spec
jev-harness skill
jev-harness init-task task.py
jev-harness check-task task.py
# 产生计费调用：指定在本地配置的私有凭据文件。
export TYPESAFE_API_KEY_FILE='/path/to/private/test-key'
jev-harness run task.py --goal 'Reach the requested target' --inputs '{"target":3}'
```

也可以通过宿主的密钥机制提供 TYPESAFE_API_KEY。绝不要提交密钥，也不要把密钥内容
写入任务脚本或 CLI 参数。init-task 创建一个自包含的合成计数器；第一个任务不需要
浏览器或桌面依赖。检查返回 JSON 中的 status/complete/archive/telemetry。
只有任务确实需要相应操作界面时，才使用[适配器](adapters.md)。

<a id="adoption-sequence"></a>
## 接入步骤

1. 阅读 `jev-harness spec`（离线 JSON）。
2. 定义目标、范围、纳入的事实/消息，以及可观察的成功条件。
3. 通过 `jev-harness init-task task.py` 生成脚本，并注册带明确签名的工具。
4. 使用 `Parameter(description, choices, depends_on=...)` 描述参数。
5. 使用合成输入测试回调行为；`check-task` 只用于静态检查。
6. 发起一次 `run` 调用；即使退出码是 2，也要解析终态数据包。
7. 由主代理补齐尚未解决的上下文，或核对执行结果不明确的情况。

需要语义分支的有界任务适合使用循环。精确计算和固定步骤留在代码中；开放式写作
交给主代理或显式的可信生成工具。工具选择决策不构成执行证明，也不构成授权。

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

提供函数的签名必须能绑定两个或三个位置参数，而不是必须具有某个固定的总参数数量。
允许可选的仅关键字参数。如果两种形式都能绑定，优先使用三个参数：带默认值的第三
参数或可变参数签名会收到 bound-arguments 对象。如果必需的仅关键字参数导致两种
形式都无法绑定，则不支持该函数。这一绑定检查不能证明提供函数的行为。

任务注册会保留动态提供函数的 callable 身份，包括其绑定的 client、锁和状态，
同时对静态候选进行深拷贝。每当一个步骤需要提供函数的候选域时，都重新调用该函数；
提供函数的结果没有缓存。

`depends_on=('customer',)` 仅在选定 customer 之后构造 job 候选域。依赖图必须无环，
并引用已存在的参数。描述参数时，应面向已选工具的下一次调用；不要要求一个值完成
整个任务。精确算术和固定值应在代码中计算；只有一个候选的域不需要推理。每个返回值
都属于实际提供过的候选。模型不能生成工具名、路径、脚本或 selector。v0.1 不提供
任意自由文本参数生成或通用 JSON Schema 验证。工具必须自行验证业务条件。

默认的分阶段绑定先选择工具，再按依赖顺序选择每个参数。只有一个候选的域直接绑定，
不调用推理。这避免了笛卡尔积膨胀。显式 `strategy='joint'` 支持小规模的完整调用
目录，用于受控比较。最多 250 个工具/调用，每个参数最多 253 个候选。
空的子候选域会请求上下文，不会猜测值。

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

<a id="terminals"></a>
## 终态

`done` 要求独立验证通过。Jev 也有类型化的 complete/blocked/missing-context 控制；
仅由模型判断完成时，状态为 `needs_review`。其他状态为 `needs_context`、
`needs_review`、`needs_confirmation`、`blocked`、`stale`、`max_steps`、
`budget_exceeded`、`execution_uncertain`、`failed`。返回的运行时数据包仅在 done
时使用退出码 0；其他返回的运行时结果使用退出码 2。中断的 CLI 任务以非零退出码
退出，不返回数据包。

执行意图在产生副作用之前持久记录。执行结果不确定时不自动重试。不保证跨运行恢复
或恰好执行一次。业务工具负责身份、幂等性、事务和外部结果核对。运行时间预算在
回调之间检查；每个回调必须自行限制 I/O 超时。推理没有结果缓存。

<a id="decision-diagnostics"></a>
## 决策诊断

终态数据包可能包含宿主生成的可选 `diagnostic`，用于尚未解决的工具或参数推理调用。
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
上下文的 `tool_id` 和 `parameter`。`telemetry.calls` 中的每个实际推理条目都带有
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
