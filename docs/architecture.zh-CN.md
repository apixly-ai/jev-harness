# 架构与参考项目

[English](architecture.md) · [任务契约](agent-contract.zh-CN.md) · [常见问题](faq.zh-CN.md)

主 AI 负责规划并编写任务脚本。确定性程序负责采集事实、准入上下文、构造工具与
参数候选域，以及验证结果。Jev 通过原生类型化接口作出选择。循环先检查状态新鲜度
与策略，再执行已注册、已绑定的动作，记录实际结果，然后继续下一轮。

运行时分开实现引擎、工具注册表、上下文投影、原生推理后端、CLI 和界面适配器。
Jev Filter 0.4.1 提供公开的类型化批处理传输接口，以及固定版本的浏览器和桌面
surface。这里不重复实现它的推理逻辑。

<a id="references-inspected"></a>

## 已查阅的参考资料

- [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast)：基于观测的动作空间、
  操作与目标选择、仅消费一次的决策，以及状态新鲜度。它专注于浏览器，文本生成交给小型 LLM。
- [burnigtm/jev-mcp](https://github.com/burnigtm/jev-mcp/blob/main/docs/tools.md)：预备好的工具调用、
  留在宿主本地的参数，以及下一步与退出契约。执行仍由其宿主负责。
- [pi agent core](https://github.com/badlogic/pi-mono/tree/main/packages/agent)：显式状态、
  消息与上下文转换，以及小而可组合的 agent 循环。
- [MellowHarness](https://github.com/Mellow-Machines-Lab/MellowHarness/blob/main/ARCHITECTURE.md)：
  事件历史、结果反馈和动态选项。它的应用侧重点与本项目不同。
- [Anthropic 上下文工程](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)：
  选择性上下文、证据引用和逐步披露。
- [TypeSafeAI/jev-harness](https://github.com/TypeSafeAI/jev-harness)：用于社区提案审查与路由的
  契约项目，并非 TypeSafe 官方团队或通用执行器。
- [parkavenue9639/jevloop](https://github.com/parkavenue9639/jevloop)：相关的 pre-alpha 运行时，
  使用有依据的参数候选、分开的会话记录与工作区投影，以及共享执行内核。
  它的 Docker/LLM 编写技术栈不是本项目的依赖。
- [zjunlp/JevLoop](https://github.com/zjunlp/JevLoop)：相关的 TypeScript 决策驱动运行时。
  我们查阅了它公开的接口，没有复现其测量结果。

以上是设计参考，不代表背书、依赖关系，也不是本运行时继承其基准测试结果的证据。
直接依赖与许可证在 [pyproject.toml](../pyproject.toml) 和 [LICENSE](../LICENSE) 中声明。
Apixly 的 Jev Harness 是独立的社区软件。
