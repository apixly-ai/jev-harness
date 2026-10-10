# Architecture and prior art

The primary AI plans and writes a task script. Deterministic code gathers facts, admits
context, constructs tool/parameter domains and verifies results. Jev makes native typed
choices. The loop executes only the registered, bound action after freshness and policy
checks, then records its actual outcome and repeats.

The runtime separates engine, tool registry, context projection, native inference backend,
CLI and surface adapters. Jev Filter 0.4.1 supplies the public typed-batch transport and
version-pinned browser/desktop surfaces. We do not duplicate its inference implementation.

## References inspected

- [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast): observed action
  spaces, operation/target choices, consumed-once decisions and state freshness. It is
  browser-specific; text generation is delegated to a small LLM.
- [burnigtm/jev-mcp](https://github.com/burnigtm/jev-mcp/blob/main/docs/tools.md): prepared
  tool calls, host-local arguments, next-step/exit contracts. Its host still executes.
- [pi agent core](https://github.com/badlogic/pi-mono/tree/main/packages/agent): explicit
  state, message/context conversion and small composable agent loops.
- [MellowHarness](https://github.com/Mellow-Machines-Lab/MellowHarness/blob/main/ARCHITECTURE.md):
  event history, outcome feedback and dynamic options. Its application focus is different.
- [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents):
  selective context, evidence references and progressive disclosure.
- [TypeSafeAI/jev-harness](https://github.com/TypeSafeAI/jev-harness): a community proposal
  review/routing contract, not the official TypeSafe team or a generic executor.

These are design references, not endorsement, dependency or evidence that this runtime
inherits their benchmark results. Direct dependencies and licenses are declared in
pyproject.toml and LICENSE. Apixly's Jev Harness is independent community software.
