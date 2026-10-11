# 浏览器与桌面工具适配器

[English](adapters.md) · [任务契约](agent-contract.zh-CN.md) · [常见问题](faq.zh-CN.md)

适配器通过同一套 Task 参数协议注册通用的、基于观测的操作。
它们展示了如何扩展运行时；具体应用的表单逻辑不放在核心代码中。

<a id="camofox-browser"></a>

## Camofox 浏览器

```python
from apixly_jev_harness import AgentLoop
from apixly_jev_harness.surfaces import browser_task

workflow = browser_task(
    url='http://127.0.0.1:8000/form.html', session='general',
    values={'traveler_name': 'Mira'},
    verify=lambda ctx, state: 'Draft ready: Mira | London | flexible=true' in state['text'],
    authorize=lambda ctx, action: action.params['arguments']['target']['label']
        in ('Flexible dates', 'Prepare draft'),
)
result = AgentLoop().run(workflow, goal='Prepare the requested local draft')
```

需要在本机回环地址上运行 Camofox REST 服务；默认使用 9378 端口与持久会话
`general`。保持 `CAMOFOX_INTERACTIVE=off`，保留 humanization 设置和浏览器身份。
浏览器负责已观测目标引用、状态新鲜度、可用性与遮挡检查，以及执行。
默认允许的来源由初始 URL 决定；产生外部影响前必须重新核验来源。
只关闭任务自己创建的标签页，不停止共享服务。

通用工具包括 click、select 和 fill。原生下拉框提供 select 候选；对其 combobox
的冗余点击会被移除。fill 只能使用调用方提供的具名值，不接受模型随意生成的
文本、脚本、选择器或坐标。即使目标是已选中的合法控件，点击仍需调用方通过
程序策略明确授权。凭证输入与交易必须由相应业务操作程序负责，不能交给这个示例适配器。

<a id="native-desktop"></a>

## 原生桌面

```python
from apixly_jev_harness.surfaces import desktop_task
workflow = desktop_task(
    window='Exact synthetic test window', process='Specific test application',
    values={'fixture_text': 'Mira'},
    verify=lambda ctx, state: 'Expected final fixture text' in state['text'],
    authorize=lambda ctx, action: allowed_fixture_action(action),
)
```

在 macOS 上安装 desktop 可选依赖。固定版本的依赖提供 Accessibility 或 Windows
UI Automation 后端与桌面安全检查。一次只指定一个具名应用或窗口；桌面必须解锁，
并具备所需权限。本项目没有宣称已通过 Windows 真实环境验收。
Mac 真实环境验收目前受锁屏阻塞，详见[验收证据](../reports/README.md)。
这里没有引入 OCR 或不受约束的坐标工具。此适配器不支持 Linux 原生桌面。

这些适配器使用固定版本 Jev Filter 依赖的内部 surface 类；升级需要回归测试和
原生环境验收。这是明确的版本依赖边界，不是跨版本稳定性承诺。
