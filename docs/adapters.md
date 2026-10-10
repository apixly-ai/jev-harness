# Browser and desktop tool adapters

Adapters register generic observed operations with the same Task parameter protocol.
They are examples of extension seams; application-specific forms do not live in core code.

## Camofox browser

```python
from jev_harness import AgentLoop
from jev_harness.surfaces import browser_task

workflow = browser_task(
    url='http://127.0.0.1:8000/form.html', session='general',
    values={'traveler_name': 'Mira'},
    verify=lambda ctx, state: 'Draft ready: Mira | London | flexible=true' in state['text'],
    authorize=lambda ctx, action: action.params['arguments']['target']['label']
        in ('Flexible dates', 'Prepare draft'),
)
result = AgentLoop().run(workflow, goal='Prepare the requested local draft')
```

A running loopback Camofox REST service is required; default base is port 9378 and durable
session general. Keep CAMOFOX_INTERACTIVE=off; preserve humanization and browser identity.
The browser owns observed target references, freshness, enablement/occlusion checks and
execution. Default allowed origins follow the initial URL. Revalidate the origin before
external effects. Close only the task-owned tab; do not stop the shared service.

Generic tools are click, select and fill. Native dropdowns expose select choices; redundant
clicks on their comboboxes are pruned. Fill uses supplied named values. No arbitrary model
text, scripts, selectors or coordinates. Clicks require explicit caller authorization by
program policy, even on a selected legitimate target. Credential entry and transactions
need their owning business operator, not this example adapter.

## Native desktop

```python
from jev_harness.surfaces import desktop_task
workflow = desktop_task(
    window='Exact synthetic test window', process='Specific test application',
    values={'fixture_text': 'Mira'},
    verify=lambda ctx, state: 'Expected final fixture text' in state['text'],
    authorize=lambda ctx, action: allowed_fixture_action(action),
)
```

Install desktop extras on macOS. The pinned dependency provides Accessibility or Windows
UI Automation backends and desktop safety gates. Target one named app/window. The desktop
must be unlocked and relevant permissions available. No live Windows acceptance is claimed.
Mac live acceptance is currently blocked by lock screen; see evidence. No OCR/unrestricted
coordinate tool is introduced here. Linux native desktop is not supported by this adapter.

These adapters use internal surface classes from the version-pinned Jev Filter dependency;
upgrades require regression and native acceptance. This dependency boundary is explicit,
not a stable cross-version claim.
