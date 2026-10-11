# Jev Harness 常见问题

[English](faq.md) · [项目概览](../README.zh-CN.md) · [任务契约](agent-contract.zh-CN.md)

这些回答介绍 Apixly 的 Jev Harness v0.1.8，并区分运行时契约、历史真实推理证据与
说明性媒体，便于读者核对每一项声明。

<a id="what-is-jev-harness"></a>

## Jev Harness 是什么？

Jev Harness 是运行 AI 编写的有界任务脚本的 Python 运行时。主 AI 定义任务并注册工具；
Jev 选择下一项已注册工具及程序提供的参数候选。程序执行已绑定动作，并独立检查目标
是否完成。它适合在明确边界内进行语义分支选择。详见[项目概览](../README.zh-CN.md)
与[架构](architecture.zh-CN.md)。

<a id="project-identity"></a>

## 这是 TypeSafe AI 官方产品，或 PyPI 上的 jev-harness 包吗？

不是。这是 Apixly 在 [apixly-ai/jev-harness](https://github.com/apixly-ai/jev-harness)
维护的独立社区软件。发行包名是 `apixly-jev-harness`，Python 命名空间是
`apixly_jev_harness`，CLI 别名是 `apixly-jev-harness` 与 `jev-harness`。
PyPI 上名为 `jev-harness` 的包属于另一个无关项目，请使用下方准确的 Git 安装地址。
[架构参考资料](architecture.zh-CN.md#references-inspected)列出了其他项目，但不代表
背书或继承其基准测试结果。

<a id="jev-filter-relationship"></a>

## Jev Harness 与 Jev Filter 有什么关系？

[Jev Filter](https://github.com/apixly-ai/jev-filter) 提供类型化的语义选择与过滤接口。
Jev Harness 围绕已注册工具、参数候选域和调用方负责的完成检查，构建有界的
观测、选择、执行、验证循环。它固定依赖 Jev Filter v0.4.1，使用其类型化批处理推理
传输接口及浏览器、桌面 surface，不重复实现推理。选择记录时可直接使用过滤接口；
需要多步、有界工具决策，并能独立观测进展的任务可使用 harness。
详见[架构](architecture.zh-CN.md)与[采用步骤](agent-contract.zh-CN.md#adoption-sequence)。

<a id="install"></a>

## 如何安装准确的 v0.1.8 版本？

需要 Python 3.10+ 与 Git。创建虚拟环境并安装带版本标签的仓库地址：

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@v0.1.8'
jev-harness spec
jev-harness init-task task.py
jev-harness check-task task.py
```

安装、`spec`、`init-task` 与 `check-task` 不调用模型，下载依赖仍需要网络。
通过 Jev 推理运行任务会计费，需要调用方通过 `TYPESAFE_API_KEY` 或
`TYPESAFE_API_KEY_FILE` 提供凭证。仅在主动开发时使用 `@main`。
运行前请遵循[首个任务说明](agent-contract.zh-CN.md#install-and-run-your-first-task)。

<a id="typed-candidates"></a>

## Jev 可以自行生成命令、选择器或工具参数吗？

不可以。Jev 只能选择已注册工具及已有参数候选。候选可以是静态值，也可以由可信的
只读 provider 根据当前观测生成。`Option(id, description, value)` 将模型可见的描述
与实际绑定值分开；`depends_on` 在父参数选定后构建子候选域。只有一个候选的域无需
推理即可绑定。模型输出不会成为可执行代码、任意文本参数、命令、路径、选择器或坐标。
业务工具仍须自行验证业务条件。详见[参数协议](agent-contract.zh-CN.md#parameter-protocol)。

<a id="suitable-tasks"></a>

## 什么任务适合使用 harness？

适合具有明确边界、有意义的语义选择、可信工具及可观测完成条件的任务，例如选择
前置工具、先收集证据再执行下一步，或准备允许操作的合成浏览器草稿。精确计算和固定
步骤交给程序；开放写作交给主 AI，或明确注册的可信生成工具。harness 没有内置通用
表单顺序，候选位置也不代表优先级；范围、前置条件与顺序由调用方提供。
详见[下一步工具选择](agent-contract.zh-CN.md#next-step-tool-selection)与
[已有案例](use-cases.zh-CN.md)。

<a id="completion"></a>

## Jev Harness 如何判断任务已完成？

只有调用方的独立验证器根据观测状态检查通过，结果才是 `done`。仅由模型声称完成会
返回 `needs_review`。选中工具、提交动作或收到工具结果，本身都不是完成证据。
通过 `result_context` 准入的安全结果摘要可以推动下一步决策，但不能替代验证。
终态包会保留阻塞、缺少上下文、需复核及执行不确定等结果。
详见[上下文与结果](agent-contract.zh-CN.md#context-and-results)及
[终态](agent-contract.zh-CN.md#terminals)。

<a id="browser-evidence"></a>

## 主页浏览器演示是 Jev 真实推理录屏吗？

MP4 与 GIF 已标明为**说明性截图回放**，由当前 headless Camofox 对未修改的本地
合成表单截图生成。它们没有新模型调用，也不是连续录屏。另有历史真实推理验收：
v0.1.0 使用 Jev 1.13.0 与 Camofox，在四次工具执行后到达最终状态，并独立检查最终
DOM 文本与字段。早期需复核及因授权门槛停止的结果也保留在证据中。没有发送真实
预订或消息。详见[媒体范围](../web/media/README.md)与[验收记录](../reports/README.md)。

<a id="desktop-support"></a>

## 浏览器与原生桌面任务是否支持，是否已经验收？

浏览器适配器使用本机回环地址上的 Camofox 服务、最新观测目标、允许来源，以及
调用方针对具体点击的授权策略。原生桌面适配器使用固定版本的 macOS Accessibility
或 Windows UI Automation 后端，并指定具名应用或窗口；该适配器不支持 Linux 原生
桌面。原生桌面完成仍未验证：Mac 验收主机处于锁屏状态，项目没有宣称通过 Windows
真实环境验收。离线适配器测试不能证明原生任务完成。
详见[适配器](adapters.zh-CN.md)与[证据边界](../reports/README.md)。

<a id="billing-and-savings"></a>

## Jev Harness 保证更省钱或更快完成吗？

不保证。真实 Jev 推理会计费。报告保留整段耗时、返回上下文、在有依据时按返回模型
分组的已知用量，以及缺少证据时的未知用量。缺少模型身份或中断的尝试不会被视为
零费用。已发布的小规模开发样例不能证明普遍的质量、延迟或成本优势。金额估算不是
发票，也不假设当前价目。各项实验的[测量范围与负面结果](../reports/README.md)可供核对。

<a id="sandbox-and-idempotency"></a>

## 运行时是沙箱吗？是否保证动作只执行一次？

不是沙箱，也没有跨运行的 exactly-once 保证。任务脚本是可信 Python；配置合法后仍会
导入脚本，并可能产生顶层副作用。静态 `check-task` 只解析和编译，不执行脚本；检查
通过不能证明运行有效。单次运行中，相同观测、动作 ID 和实际绑定参数的重复执行会
在执行前被阻止；这是一项执行保护，不是跨运行只执行一次或恢复运行的保证。
调用方业务工具负责身份、授权、幂等、事务及外部状态核对。不确定的动作不会自动重试。
详见[静态检查](agent-contract.zh-CN.md#static-task-checking)、
[执行上下文](context.zh-CN.md)与[终态](agent-contract.zh-CN.md#terminals)。

<a id="execution-limits"></a>

## 任务编写者需要落实哪些执行与上下文边界？

推理不缓存结果，独立推理并发最多 30。同步运行时在回调之间检查墙钟时间预算；每项
工具须自行限制 I/O 与轮询。固定观测下不支持重复调用同一个动作。默认上下文策略
保留最近八次已准入的动作结果及较早动作的记录；如果准入上下文仍超过保守的
15,000 字符预算，会返回复核，而不会悄悄丢弃约束。原始证据留在私有日志中，仅准入
安全摘要。详见[上下文管理](context.zh-CN.md)与
[同步回调契约](agent-contract.zh-CN.md#synchronous-callback-contract)。
