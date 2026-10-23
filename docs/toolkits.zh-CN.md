# 可复用工具包与薄任务脚本

[English](toolkits.md) · [任务契约](agent-contract.zh-CN.md) · [使用案例](use-cases.zh-CN.md)

定义目标，组合一次来源工具，就可以让 Jev 探索运行中才发现的链接、文件与证据。
路线和后续参数可以未知。任务脚本提供范围、完成检查和资源边界，不编写下一步 router。

本页说明工具包接口和可运行薄脚本。实测运行与范围见
[验收账本](../reports/README.zh-CN.md)及
[工具包真实报告](../reports/toolkit-live-2026-10-11.json)。示例本身不证明普遍语义质量、
提速或费用优势。

<a id="compose-the-public-interfaces"></a>
## 组合公共接口

| 接口 | 职责 |
| --- | --- |
| EvidenceStore | 在进程中保留采集文本，提供出处、小摘要和有界段落引用 |
| WebTools(provider, store) | 发现当前链接/章节，跟随已观察链接并读取采集章节 |
| HttpProvider / CamofoxProvider | 在调用方来源范围内采集 HTTP 文本或浏览器渲染文本 |
| WorkspaceTools(root, store, queries=...) | 发现、搜索、读取允许的本地普通文件，不执行其源码 |
| EvidenceTask | 组合注册工具、段落读取、证据分类和独立核验的已保存报告 |
| TaskScript(build) | 根据已校验的运行时 inputs，延迟构建一次注册任务 |
| ToolkitSession | 用同一任务支持直接引用操作，或一次 Jev 委托 |
| Engine().decide(records, goal=..., analysis_spec=...) | 用类型化问题批量判断大量记录；用 `init-task --toolkit records` 生成脚手架 |
| SurfaceTask(surface, ..., allow=..., tools=...) | 对已观察控件点击/选择/填写；`allow(target)` 收窄可选控件；用 `init-task --toolkit surface` 生成脚手架 |

工具包提供 name、observe() 和 install(task)。观察是简洁、稳定的投影；观察或提供
参数不会创建新来源 capture。EvidenceTask 首次观察会执行一次声明的 prepare()；
WorkspaceTools.prepare() 只做有界文件元数据发现，不读取源码正文、不创建证据 capture，
使当前文件候选可用。采集发生在工具执行期间；例外是延迟 factory 首次构建
WebTools 时，会采集入口来源。Provider 通过普通 Task 协议提供有意义的 Option 描述
和新参数域。

<a id="start-with-a-thin-script"></a>
## 从薄脚本开始

[网页调研](../examples/research_task.py)和
[仓库调查](../examples/workspace_task.py)均导出 workflow = TaskScript(build)。源码
不包含目标答案或规定探索顺序。build(inputs) 接收运行时配置，定义 store、工具包、
证据类别、输出位置和调用方 verifier。

| inputs 字段 | 含义 |
| --- | --- |
| markers | 必需的非空 object，将引用类别 label 映射到非空 marker 字符串 |
| output | 调用方拥有的新报告路径，不默默覆盖已有输出 |
| 网页 url、allowed_origins | 允许的入口及来源范围 |
| 仓库 root、可选 queries | 允许的源码目录和初始字面搜索词 |

示例 verifier 使用输入 marker 检查每个所需类别的采集引用。record_checks 将 label
映射到返回严格 bool 的段落检查，只提供已有读片段支持的类别；先选 label，再解析
依赖的 passage。这筛选合法引用，不决定下一项工具。它演示验证接入点，业务
身份、适用性、时效和证据质量仍由调用方检查。EvidenceTask 先核对真实保存产物与当前
记录一致，再把含完整引用文本的**全部 records**交给 verifier，而不是简短决策投影。
artifact_receipt() 返回路径、是否存在、是否匹配、记录数、digest 和来源列表，便于
调用方核对已保存结果。

在安装了包的仓库 checkout 中，把以下示意输入替换成允许的测试来源和判定条件：

```sh
jev-harness check-task examples/research_task.py
jev-harness run examples/research_task.py --goal 'Investigate the requested categories and save sourced quotes' --inputs '{"url":"https://docs.example.org/","allowed_origins":["https://docs.example.org"],"markers":{"requirements":"<source marker>"},"output":"local-results/research.json"}' --max-steps 20 --timeout 120
```

check-task 是静态检查；run 可采集来源，Jev 推理付费，凭据留在调用方配置环境中。
公开付费验收使用本地合成数据，其他数据集的范围与授权由调用方负责。

<a id="read-evidence-progressively"></a>
## 按需读取证据

store.put(text, source, metadata) 返回本次 capture 引用。describe(ref) 和 references()
提供来源、长度、完整 SHA-256、最多 240 字符的摘要和元数据。read(ref, offset, limit) 返回最多 1,200 字符
的原文窗口。chunk_options() 提供段落候选，EvidenceTask 另提供段落分页选择。

完整采集文本保留在 store。共享 evidence 来源索引保留最后八个引用、来源、长度及
最多 80 字符的摘要，工具包来源引用不再重复这些摘要；完整 SHA-256 和元数据仍保留
在本地 store。Jev 另收到近期记录摘要、计数及最多 1,200 字符的 last_read。较早 capture 仍可通过引用和动态段落候选读取。这是进程内
capture，不是自动持久化的原文归档。已保存报告包含所选记录与出处，新进程不能续接
旧 store 或 session。已有 loop 上下文预算仍可能停止过大的投影。

共享证据工具为 read_evidence、evidence_page、record_evidence、save_report；来源
工具包括 web.open_link、web.read_section、files.list、files.search、files.read。
Jev 选择何时调查、阅读、记录或保存；程序负责引用解析、来源采集和真实执行。

<a id="discovery-and-matching"></a>
## 探索与匹配

选择值得探索的来源或规划下一项调查时，使用 Parameter(..., selection="explore")。
未知目的地不必已经证明目标。默认 selection="match" 保留原匹配策略：top probability
0.55、margin 0.10。EvidenceTask 的工具选择及 explore 参数选择使用 top probability
0.30、margin 0.0，其他检查保留。这些默认值来自小范围开发校准，不代表已证明质量
提升，也不提供执行授权。

没有推理/结果缓存。Jev 选择已提供引用，工具包没有内置自由文本生成。查询或文章
可以由明确注册的可信 generator 生成，经校验后进入候选池；生成文本不直接成为代码、
命令或 selector。

<a id="use-the-same-task-through-mcp"></a>
## 用 MCP 接入同一任务

使用薄脚本和相同运行时 inputs schema 启动 stdio 服务：

```sh
python -m apixly_jev_harness.mcp examples/workspace_task.py --goal 'Investigate source evidence and save quotes' --inputs '{"root":"permitted-corpus","queries":["relevant_identifier"],"markers":{"implementation":"<source marker>"},"output":"local-results/workspace.json"}' --context '{}' --max-steps 20 --timeout 120 --archive local-results/session.jsonl
```

| MCP 工具 | 操作 |
| --- | --- |
| observe | 查看当前状态、可用工具契约和参数引用 |
| arguments | 带当前 state_ref 查看参数候选，传入父引用后解析依赖子候选 |
| operate | 带当前 state_ref 与已提供参数 ID 执行一项工具 |
| run_task | 在 session 预算内把注册任务交给 Jev loop |
| read_report | 每页读取最多四条已保存且匹配的原始引用，不执行任务工具或推理 |

每个广告的工具都明确声明四个布尔值 [MCP annotation hints](https://modelcontextprotocol.io/specification/2025-06-18/schema#toolannotations)。
`observe` 和 `arguments` 会调用使用方定义的观察、准备、校验或候选回调，这些回调可能
执行 I/O 或改变状态。因此它们与 `operate`、`run_task` 一样保守声明：
`readOnlyHint: false`、`destructiveHint: true`、`idempotentHint: false`、`openWorldHint: true`。
这描述通用回调契约可能具备的行为，不表示每次检查都会执行破坏性动作。
`read_report` 仅核对并读取已保存的本地报告，四项依次为 `true`、`false`、`true`、`false`。
这些提示不构成动作授权，也不替代新鲜度、权限、不可逆动作门禁或独立完成检查。
实际工具列表为三至五项：`--direct-only` 不广告执行工具，只有证据任务或延迟加载的
task script 才广告报告读取工具。
[固定合成 stdio A/B](../reports/mcp-annotations-ab.json) 核对列表提示、回调与动作一致性
及本地协议字节数，未调用模型；它不是安全审计。

对于带依赖的工具，调用 arguments 时传入工具名和已选父引用 ID，再从返回域选子候选。
operate 需要当前提供的全部参数 ID；广告的 MCP arguments/operate 还必须带最近
observe.state_ref 中的指纹。操作后刷新观察，一个 session 内顺序执行。旧状态、未提供
或重复操作会被拒绝。既有 Python 方法的 state_ref 保持可选兼容，MCP 客户端必传。

MCP 发现接口会按绑定目标描述执行工具、inputs、权限、独立检查和步数/时间边界，
不为此加载延迟 factory 或运行推理。outputSchema 描述终态、完成状态、遥测及可选
artifact/report 字段；成功工具响应同时提供 JSON 文本和 structuredContent。
initialize.instructions 事实性说明两条路线：operate 执行一项注册工具，run_task 让
Jev 根据现场选择工具和新参数引用完成整项任务，不规定 AI 必须选择哪条路线。

调用方可用 --execution-name investigate_sources 按任务命名执行动作。名称以小写
字母开头，后接小写字母、数字或下划线，最多 64 字符，不能与其他 MCP 工具重名。
标题和描述仍明确标识 Jev Harness 与 Jev loop，不因改名隐藏决策执行方。

观察还包括委托是否就绪、当前目标、使用相同 tools/verifier 的声明以及产物 receipt。
Python 调用方使用 session.delegate()；旧 MCP delegate 名称作为不广告的兼容别名
保留，对应 run_task。

从 v0.2.1 起，run_task 可以是 TaskScript 的首次 session 调用。Loop 构建注册任务后，
若该任务提供 artifact_receipt()，会将回执转发到终态 artifact 字段；调用方无需为了
获得回执而先调用 observe。证据任务还返回首个报告页；read_report 传 {"page": 1}
读取后续页，结合 has_more/pages 继续分页。每页最多四条原始引用，含来源引用、
字符窗口及 SHA-256；只有保存产物仍匹配任务 records 才返回正文，否则返回
available: false 和空引用。两条路线结束后均可只读回查，不恢复执行、不调用推理。
这些接口让两条路线都可核查，不代表 AI 已被证明会自然选择托管。

在 session 开始时选择直接操作或 Jev 委托，可以先查看接口，但执行后不能切换路线或
合并两种历史。--direct-only 隐藏委托。这是进程内 session，不提供跨进程 resume；
直接模式的调用方模型费用不在 Jev 遥测内。应查看终态证据并核对不确定执行，不盲目重试。

<a id="source-specific-boundaries"></a>
## 来源边界

HttpProvider 只用 GET，有界读取响应并逐跳检查来源，提取服务端 HTML/文本。需要
浏览器渲染文本时，把调研脚本中的 provider 换成：

```python
provider = jev.CamofoxProvider(
    url=inputs["url"], allowed_origins=inputs["allowed_origins"],
    session=inputs["session"], tab=inputs["tab"],
)
```

共享 Camofox 服务保持 headless（CAMOFOX_INTERACTIVE=off）和 humanize: true，复用
固定具名 session/tab 身份。只关闭任务拥有的 tab；调用方提供的已有 tab 仍由调用方
拥有。浏览器检查约束候选目的地和最终观察来源，不是重定向或子资源的网络防火墙。
进程内调用方结束后应关闭来源工具包；MCP 服务在 session 结束时关闭自己的工具包。

Workspace 读取限定于选定 root，拒绝 symlink，不 import 或执行被查看源码；需要安全
的 descriptor-relative open，不支持它的 Windows 等平台会 fail closed。文件/搜索边界
和遗漏显式返回。来源工具包不是 Python 沙箱，调用方范围和独立完成检查仍必需。
