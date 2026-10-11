"""Build static, crawlable documentation and an evidence-bound landing page."""

import html
import json
import re
import shutil
from pathlib import Path

import markdown

from apixly_jev_harness import __version__ as VERSION

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site"
BASE = "https://apixly-ai.github.io/jev-harness/"
REPO = "https://github.com/apixly-ai/jev-harness"
PAGES = {
    "agent-contract": ("docs/agent-contract.md", "AI-native task contract"),
    "context": ("docs/context.md", "Context management"),
    "adapters": ("docs/adapters.md", "Browser and desktop adapters"),
    "architecture": ("docs/architecture.md", "Architecture and references"),
    "evidence": ("reports/README.md", "Acceptance evidence"),
}


def shell(title, description, body, path="", lang="en"):
    prefix = "../" if path.startswith("zh/") else ""
    canonical = BASE + path
    alternate = (
        f'<link rel="alternate" hreflang="en" href="{BASE}"><link rel="alternate" hreflang="zh-CN" href="{BASE}zh/">'
        if path in ("", "zh/")
        else ""
    )
    data = {
        "@context": "https://schema.org",
        "@type": "SoftwareSourceCode",
        "name": "Jev Harness",
        "description": description,
        "codeRepository": REPO,
        "url": BASE,
        "programmingLanguage": "Python",
        "license": REPO + "/blob/main/LICENSE",
        "version": VERSION,
        "author": {
            "@type": "Organization",
            "name": "Apixly",
            "url": "https://github.com/apixly-ai",
        },
    }
    page = f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)} · Jev Harness</title><meta name="description" content="{html.escape(description, quote=True)}"><link rel="canonical" href="{canonical}">{alternate}<meta property="og:title" content="{html.escape(title, quote=True)}"><meta property="og:description" content="{html.escape(description, quote=True)}"><meta property="og:url" content="{canonical}"><meta property="og:type" content="website"><meta property="og:image" content="{BASE}{"brand/social.zh-CN.png" if lang == "zh-CN" else "social.png"}"><link rel="stylesheet" href="{prefix}style.css"><script type="application/ld+json">{json.dumps(data)}</script></head><body><nav><a class="brand" href="{prefix}{"zh/" if lang == "zh-CN" else "index.html"}"><svg class="brand-glyph" viewBox="0 0 36 36" aria-hidden="true" fill="none"><path d="M5 14V5h12m-4-4 4 4-4 4M22 5h9v12m-4-4 4 4 4-4" stroke="#c6f67a" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M31 22v9H19m4-4-4 4 4 4M14 31H5V19m-4 4 4-4 4 4" stroke="#7de3e5" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg> jev<span> / harness</span></a><a href="{prefix}{"zh/" if lang == "zh-CN" else "index.html"}#showcase">Showcase</a><a href="{prefix}agent-contract.html">Agent contract</a><a href="{prefix}context.html">Context</a><a href="{prefix}evidence.html">Evidence</a><a href="{REPO}">GitHub ↗</a><a href="{prefix}{"index.html" if lang == "zh-CN" else "zh/"}">{"EN" if lang == "zh-CN" else "中文"}</a></nav>{body}<footer><span>Jev Harness · Apixly independent community project · MIT</span><span>Not an official TypeSafe AI product. Early {VERSION}.</span></footer></body></html>'''
    if lang == "zh-CN":
        for old, new in [
            (">Showcase<", ">演示案例<"),
            (">Agent contract<", ">任务协议<"),
            (">Context<", ">上下文<"),
            (">Evidence<", ">验收证据<"),
            ("Apixly independent community project", "Apixly 独立社区项目"),
            (
                f"Not an official TypeSafe AI product. Early {VERSION}.",
                f"非 TypeSafe AI 官方产品。早期 {VERSION}。",
            ),
        ]:
            page = page.replace(old, new)
    return page


def home(zh=False):
    p = "../" if zh else ""

    def t(en, cn):
        return cn if zh else en

    icon = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 9V5h4M15 5h4v4M19 15v4h-4M9 19H5v-4M9 9h6v6H9z" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    lead = t(
        "Turn a task into a loop that can act. You define the tools and choices. Jev picks the next step. Your code checks the result.",
        "把任务变成可以执行的循环。你定义工具与候选，Jev 选择下一步，程序执行并核对结果。",
    )
    install = f"pip install 'git+https://github.com/apixly-ai/jev-harness.git@v{VERSION}'"
    language = ".zh-CN" if zh else ""
    body = f'''
<main class="wrap home">
  <section class="hero" aria-labelledby="hero-title">
    <div class="hero-copy">
      <div class="eyebrow"><span class="status-dot"></span> {t("A SMALL RUNTIME. A COMPLETE LOOP.", "轻量运行时，完整执行循环。")}</div>
      <h1 id="hero-title">{t("Your tools.<br><em>Jev’s next move.</em>", "工具你来定义。<br><em>下一步交给 Jev。</em>")}</h1>
      <p class="hero-lead">{lead}</p>
      <div class="actions"><a class="button" href="#showcase">{t("Watch it work", "看看它怎么做")} <span aria-hidden="true">↗</span></a><a class="button secondary" href="#start">{t("Build your first task", "开始编写任务")} <span aria-hidden="true">→</span></a></div>
      <div class="hero-meta"><span>Python 3.10+</span><span>MIT</span><span>v{VERSION}</span></div>
    </div>
    <div class="control-room" role="img" aria-label="{t("Loop illustration: observe a travel form, choose from registered tools, bind a supplied candidate and independently verify the draft.", "执行循环示意：观察旅行表单，选择注册工具，绑定已提供候选，独立验证草稿。")} ">
      <div class="room-head"><span>{icon} TASK CONTROL ROOM</span><span class="mini-badge">{t("LOOP ILLUSTRATION", "循环示意")}</span></div>
      <div class="goal-line"><span class="room-label">{t("GOAL", "目标")}</span><strong>{t("Prepare Mira’s London travel draft", "为 Mira 准备伦敦旅行草稿")}</strong></div>
      <div class="room-workspace">
        <div class="context-stack"><div class="room-label">{t("OBSERVED STATE", "当前观察")}</div><div class="context-line"><span>traveler</span><b class="empty">—</b></div><div class="context-line"><span>destination</span><b>London</b></div><div class="context-line"><span>flexible</span><b class="cyan">true</b></div><div class="room-label context-note">{t("PROGRAM-SUPPLIED TOOLS", "程序注册工具")}</div><div class="tool-option">inspect</div><div class="tool-option chosen">type <span>← Jev</span></div><div class="tool-option">select</div><div class="tool-option">click</div></div>
        <div class="decision-column"><div class="decision-core">{icon}<strong>Jev</strong><small>{t("chooses the next call", "选择下一次调用")}</small></div><div class="bound-call"><span class="room-label">{t("BOUND CALL", "绑定后的调用")}</span><code>type(target=<b>name</b>,<br> value=<b>"Mira"</b>)</code></div></div>
      </div>
      <div class="verify-line"><span class="check-mark">✓</span><div><strong>{t("Completion needs evidence.", "完成，需要结果证据。")}</strong><small>{t("Read the fields. Check the final DOM.", "回读字段，核对最终 DOM。")}</small></div><span class="verify-pulse"></span></div>
      <div class="loop-rail" aria-hidden="true"><span>01 {t("Observe", "观察")}</span><span>02 {t("Choose", "选择")}</span><span>03 {t("Execute", "执行")}</span><span>04 {t("Verify", "验证")}</span></div>
    </div>
  </section>
  <div class="principle-strip"><span>{t("THE CONTRACT IS YOURS", "契约由你定义")}</span><p>{t("Registered tools", "注册工具")}<i> / </i>{t("Supplied candidates", "提供候选")}<i> / </i>{t("Verified outcomes", "验证结果")}</p><button class="motion-control" type="button" aria-pressed="false" data-pause="{t("Pause motion", "暂停动画")}" data-resume="{t("Resume motion", "播放动画")}" hidden>{t("Pause motion", "暂停动画")} <span aria-hidden="true">Ⅱ</span></button></div>
  <section class="section showcase" id="showcase" aria-labelledby="showcase-title">
    <div class="section-heading"><div><div class="eyebrow">01 / {t("SEE THE LOOP", "看执行过程")}</div><h2 id="showcase-title">{t("Less explaining.<br>More showing.", "让案例，<br>把过程讲清楚。")}</h2></div><p>{t("A browser draft, a typed Python task, and the guards that keep a loop honest. Pick a case and look inside.", "浏览器草稿、类型化 Python 任务，以及执行边界。选一个场景，看清输入、选择和结果。")}</p></div>
    <div class="case-tabs" role="tablist" aria-label="{t("Use cases", "使用场景")}" hidden><button type="button" role="tab" id="tab-browser" aria-controls="case-browser" aria-selected="true" tabindex="0"><span>01</span>{t("Browser workflow", "浏览器任务")}</button><button type="button" role="tab" id="tab-python" aria-controls="case-python" aria-selected="false" tabindex="-1"><span>02</span>{t("Typed tool choices", "工具与参数选择")}</button><button type="button" role="tab" id="tab-guards" aria-controls="case-guards" aria-selected="false" tabindex="-1"><span>03</span>{t("Completion guards", "完成与执行边界")}</button></div>
    <article class="case-panel" id="case-browser" role="tabpanel" aria-labelledby="tab-browser">
      <div class="demo-frame"><div class="frame-top"><span class="window-dots"><i></i><i></i><i></i></span><span>travel-request / local fixture</span><span class="frame-badge">{t("SCREENSHOT REPLAY", "截图回放")}</span></div><video id="browser-video" controls loop muted playsinline preload="none" poster="{p}media/browser-poster{language}.webp" aria-label="{t("Screenshot replay of the synthetic browser travel-draft fixture", "合成浏览器旅行草稿夹具的截图回放")}"><source src="{p}media/browser-demo{language}.mp4" type="video/mp4"><a href="{p}media/browser-demo{language}.mp4">{t("Download the replay", "下载回放")}</a></video><div class="media-caption">{t("New screenshot replay of the local fixture. Historical Jev acceptance is linked separately; this replay makes no model calls.", "本地夹具的截图回放，不调用模型；历史 Jev 真实验收见旁边证据链接。")}</div></div>
      <div class="case-copy"><div class="case-kicker"><span class="status-dot"></span>{t("BROWSER / SYNTHETIC FIXTURE", "浏览器 / 合成夹具")}</div><h3>{t("From an empty form<br>to a checked draft.", "从空白表单，<br>到核对完成的草稿。")}</h3><p>{t("Fill the traveler, choose the destination, set flexible dates, and prepare the draft. Completion requires both field values and final result text.", "填写旅客、选择目的地、勾选灵活日期，再生成草稿。只有字段值和最终结果文字都符合要求，才算完成。")}</p><dl class="case-details"><div><dt>{t("INPUT", "输入")}</dt><dd>Mira · London · flexible=true</dd></div><div><dt>{t("CHOICES", "候选")}</dt><dd>{t("Observed controls + supplied values", "观察到的控件 + 程序提供的值")}</dd></div><div><dt>{t("CHECK", "验证")}</dt><dd>Draft ready: Mira | London | flexible=true</dd></div></dl><a class="text-link" href="{p}evidence.html">{t("Inspect historical live acceptance", "查看历史真实验收")} <span aria-hidden="true">↗</span></a><p class="case-footnote">{t("v0.1.0 · real Jev + headless Camofox · 4 tool executions · local synthetic data; no booking sent.", "v0.1.0 · 真实 Jev + 无头 Camofox · 4 次工具执行 · 本地合成数据，未发送真实预订。")}</p></div>
    </article>
    <article class="case-panel" id="case-python" role="tabpanel" aria-labelledby="tab-python" hidden>
      <div class="code-demo"><div class="frame-top"><span class="window-dots"><i></i><i></i><i></i></span><span>task.py / typed parameters</span><span class="frame-badge">{t("ILLUSTRATION", "机制示意")}</span></div><pre><span class="code-muted"># {t("Only supplied values can be selected", "只从程序提供的候选中选择")}</span>
workflow = <b>Task</b>(observe=observe, verify=verify)

@workflow.<b>tool</b>("Advance without overshooting",
    parameters={{"amount": <b>Parameter</b>(
        "Amount needed for the next increment",
        <i>lambda</i> ctx, seen: [n <i>for</i> n <i>in</i> (1, 2)
            <i>if</i> seen["value"] + n &lt;= seen["target"]]
    )}})
<i>def</i> increment(amount):
    state["value"] += amount
    <i>return</i> {{"value": state["value"]}}</pre><div class="counter-path"><span>0</span><i>+1</i><span>1</span><i>+2</i><span class="counter-done">3 ✓</span></div><p class="media-caption">{t("Illustrated candidate path; an example sequence, not a recorded inference run.", "候选路径示意；这是示例序列，不是推理录屏。")}</p></div>
      <div class="case-copy"><div class="case-kicker">PYTHON / TYPED CHOICES</div><h3>{t("The model chooses.<br>Your program binds.", "模型选择引用，<br>程序绑定实际值。")}</h3><p>{t("A small counter makes parameter meaning visible. Candidate domains come from current state; the final verifier checks the target instead of trusting a model claim.", "用小型计数器看清参数含义：从当前状态生成候选，最后由验证器检查是否达到目标。")}</p><dl class="case-details"><div><dt>{t("INPUT", "输入")}</dt><dd>value=0 · target=3</dd></div><div><dt>{t("CHOICES", "候选")}</dt><dd>amount ∈ {{1, 2}} · {t("no overshooting", "不超过目标")}</dd></div><div><dt>{t("CHECK", "验证")}</dt><dd>observed value == target</dd></div></dl><a class="text-link" href="{p}agent-contract.html">{t("Read the task contract", "查看任务契约")} ↗</a><p class="case-footnote">{t("Historical generated-task acceptance and early review outcomes are retained in the evidence ledger.", "验收账本保留生成任务的历史真实结果与早期复核结果。")}</p></div>
    </article>
    <article class="case-panel" id="case-guards" role="tabpanel" aria-labelledby="tab-guards" hidden>
      <div class="guard-demo"><div class="frame-top"><span class="window-dots"><i></i><i></i><i></i></span><span>runtime / terminal outcomes</span><span class="frame-badge">{t("OFFLINE CASES", "离线案例")}</span></div><div class="guard-states"><div class="guard-row"><span class="guard-icon lime">✓</span><div><strong>done</strong><p>{t("The independent verifier passes.", "独立验证器确认完成。")}</p></div><code>verified state</code></div><div class="guard-row"><span class="guard-icon amber">!</span><div><strong>blocked</strong><p>{t("The same action and state repeat.", "相同状态与动作重复出现。")}</p></div><code>repeated_action_state</code></div><div class="guard-row"><span class="guard-icon cyan">?</span><div><strong>needs_review</strong><p>{t("A decision cannot be resolved.", "无法确定工具或参数选择。")}</p></div><code>automatic_retry: false</code></div></div><p class="media-caption">{t("Examples from synthetic offline contracts. Unknown effects and usage remain explicit.", "合成离线契约示例；不确定效果与未知用量保留为不确定。")}</p></div>
      <div class="case-copy"><div class="case-kicker">EVIDENCE / EXECUTION BOUNDS</div><h3>{t("A useful loop also<br>knows when to stop.", "能推进任务，<br>也知道何时停下。")}</h3><p>{t("Admitted tool results can advance the next decision. A repeated call against the same state stops before execution. Unresolved choices return a review outcome.", "准入的工具结果可以推进下一轮判断；相同状态下重复调用会在执行前阻断，无法确定的选择则返回复核。")}</p><dl class="case-details"><div><dt>{t("INPUT", "输入")}</dt><dd>{t("Observation + admitted results + ledger", "观察 + 准入结果 + 动作账本")}</dd></div><div><dt>{t("BOUND", "边界")}</dt><dd>{t("Registered tools and supplied arguments", "注册工具与已提供参数")}</dd></div><div><dt>{t("CHECK", "验证")}</dt><dd>{t("Continue, finish, block or review", "继续、完成、阻断或复核")}</dd></div></dl><a class="text-link" href="{p}evidence-progress-ab.json">{t("Open the offline A/B report", "打开离线 A/B 报告")} ↗</a><p class="case-footnote">{t("Offline scripted decisions establish guard behavior; they do not prove live semantic performance.", "离线脚本决策验证边界行为，不证明真实语义表现。")}</p></div>
    </article>
  </section>
  <section class="section how" id="how" aria-labelledby="how-title"><div class="section-heading"><div><div class="eyebrow">02 / {t("UNDER THE HOOD", "运行机制")}</div><h2 id="how-title">{t("Four steps.<br>One clear responsibility each.", "四个环节，<br>各司其职。")}</h2></div><a class="text-link" href="{p}architecture.html">{t("Explore the architecture", "查看架构")} ↗</a></div><div class="loop"><div><small>01 / OBSERVE</small><strong>{t("Bring the context", "提供上下文")}</strong><p>{t("Goal, current state, admitted dialogue and action history.", "目标、当前状态、准入对话与执行历史。")}</p></div><div><small>02 / CHOOSE</small><strong>{t("Choose the next step", "选择下一步")}</strong><p>{t("Jev selects registered tools and meaningful parameter candidates.", "Jev 选择注册工具与有语义的参数候选。")}</p></div><div><small>03 / EXECUTE</small><strong>{t("Bind and execute", "绑定并执行")}</strong><p>{t("Your code binds real values and applies freshness and policy checks.", "程序绑定实际值，检查新鲜度与执行策略。")}</p></div><div><small>04 / VERIFY</small><strong>{t("Check the outcome", "核对结果")}</strong><p>{t("An independent verifier decides whether the task is complete.", "独立验证器判断任务是否真正完成。")}</p></div></div></section>
  <section class="section capabilities"><div class="capability-intro"><div class="eyebrow">03 / {t("BUILT TO FIT YOUR CODE", "融入你的程序")}</div><h2>{t("Small surface.<br>Useful building blocks.", "接口轻巧，<br>能力可组合。")}</h2><p>{t("Keep your business logic in your tools. Reuse the runtime around them.", "业务逻辑留在工具里，外围循环交给可复用运行时。")}</p><a class="text-link" href="{p}adapters.html">{t("Browser & desktop adapters", "浏览器与桌面适配器")} ↗</a></div><div class="capability-grid"><article class="card"><div class="feature-icon">{{ }}</div><h3>{t("Meaning before values", "先描述语义，再绑定值")}</h3><p>{t("Typed options, dynamic domains and ordered parameter dependencies.", "类型化选项、动态候选域与顺序解析的参数依赖。")}</p></article><article class="card"><div class="feature-icon">↳</div><h3>{t("Context that stays useful", "保留有用的工作状态")}</h3><p>{t("Constraints, recent admitted results and references to older evidence.", "保留约束、近期准入结果及较早证据引用。")}</p></article><article class="card"><div class="feature-icon">&gt;_</div><h3>{t("An agent-ready interface", "AI 可直接使用的接口")}</h3><p>{t("Machine-readable spec, task scaffold, static checks and a bundled skill.", "机器可读 spec、任务模板、静态检查与随包提供的 skill。")}</p></article><article class="card"><div class="feature-icon">◎</div><h3>{t("Evidence you can inspect", "可以复查的证据")}</h3><p>{t("Intent, actual outcomes and unknown usage remain in the ledger.", "执行意图、实际结果与未知用量保留在账本中。")}</p></article></div></section>
  <section class="evidence-band"><div class="evidence-icon">↗</div><div><div class="eyebrow">{t("OPEN EVIDENCE", "公开证据")}</div><h3>{t("Show the result. Keep the limits.", "结果可查，边界说清。")}</h3><p>{t("Historical live browser fixture verified. Desktop adapters have offline tests; native desktop completion remains unverified. No universal success or savings claim.", "历史真实浏览器夹具已验证；桌面适配器已有离线测试，原生桌面完成仍未验证。不承诺普遍成功或节省费用。")}</p></div><a class="button secondary" href="{p}evidence.html">{t("Read the evidence", "查看验收记录")} ↗</a></section>
  <section class="section start" id="start" aria-labelledby="start-title"><div class="start-copy"><div class="eyebrow">04 / {t("MAKE IT YOURS", "开始使用")}</div><h2 id="start-title">{t("Your first loop<br>starts with a contract.", "第一个循环，<br>从一份契约开始。")}</h2><p>{t("Install in a virtual environment. Inspect the spec, create a task, check it offline, then run with your own goal.", "在虚拟环境中安装，查看规范、生成任务、离线检查，再按自己的目标运行。")}</p><div class="actions"><a class="text-link" href="{p}agent-contract.html">{t("Installation & task protocol", "安装与任务协议")} ↗</a><a class="text-link" href="{p}spec.json">spec.json ↗</a></div><p class="small">{t("Inference is billable. Trusted Python scripts; the runtime is not a sandbox.", "推理付费。执行可信 Python 脚本；运行时不是沙箱。")}</p></div><div class="editor"><div class="editor-head"><span>terminal</span><button class="copy-button" type="button" data-copy="{html.escape(install, quote=True)}" data-copied="{t("Copied", "已复制")}" hidden>{t("Copy install", "复制安装命令")}</button></div><pre><span class="code-muted"># {t("Create a virtual environment", "创建虚拟环境")}</span>
python -m venv .venv
. .venv/bin/activate

<span class="code-muted"># {t("Install the pinned version", "安装固定版本")}</span>
{html.escape(install)}

jev-harness <b>spec</b>
jev-harness <b>init-task</b> task.py
jev-harness <b>check-task</b> task.py
<span class="code-muted"># {t("Configure TYPESAFE_API_KEY in your environment", "在环境中配置 TYPESAFE_API_KEY")}</span>
jev-harness <b>run</b> task.py \\
  --goal "Reach target" --inputs '{{"target":3}}'</pre></div></section>
  <section class="related"><span>{t("PART OF YOUR TOOLKIT", "工具箱里的其他项目")}</span><a href="https://apixly-ai.github.io/jev-filter/"><b>Jev Filter</b><small>{t("Find the signal in many records", "从多条记录中筛选信号")}</small>↗</a><a href="https://github.com/JIA-ss/ai-remote"><b>ai-remote</b><small>{t("MCP access to your computers", "通过 MCP 访问你的电脑")}</small>↗</a></section>
</main><script src="{p}home.js" defer></script>'''
    return shell(
        t("Your tools. Jev’s next move.", "工具你来定义，下一步交给 Jev。"),
        lead,
        body,
        "zh/" if zh else "",
        "zh-CN" if zh else "en",
    )


def rewrite_links(content):
    mapping = {
        "architecture.md": "architecture.html",
        "context.md": "context.html",
        "adapters.md": "adapters.html",
        "agent-contract.md": "agent-contract.html",
        "acceptance.json": "acceptance.json",
        "parameter-prompt-ab.json": "parameter-prompt-ab.json",
        "parameter-ab.json": "parameter-ab.json",
        "evidence-progress-ab.json": "evidence-progress-ab.json",
        "../reports/evidence-progress-ab.json": "evidence-progress-ab.json",
        "decision-diagnostics-ab.json": "decision-diagnostics-ab.json",
        "../reports/decision-diagnostics-ab.json": "decision-diagnostics-ab.json",
        "tool-choice-offline-ab.json": "tool-choice-offline-ab.json",
        "tool-choice-live-ab.json": "tool-choice-live-ab.json",
        "../reports/tool-choice-offline-ab.json": "tool-choice-offline-ab.json",
        "../reports/tool-choice-live-ab.json": "tool-choice-live-ab.json",
        "static-check-ab.json": "static-check-ab.json",
        "../reports/static-check-ab.json": "static-check-ab.json",
        "run-preflight-ab.json": "run-preflight-ab.json",
        "../reports/run-preflight-ab.json": "run-preflight-ab.json",
        "callback-contract-ab.json": "callback-contract-ab.json",
        "../reports/callback-contract-ab.json": "callback-contract-ab.json",
        "task-output-ab.json": "task-output-ab.json",
        "../reports/task-output-ab.json": "task-output-ab.json",
        "cli-arguments-ab.json": "cli-arguments-ab.json",
        "../reports/cli-arguments-ab.json": "cli-arguments-ab.json",
    }

    def replace(match):
        href = match.group(1)
        if href.startswith(("http:", "https:", "#")):
            return match.group(0)
        target = mapping.get(href)
        if target:
            return f'href="{target}"'
        return f'href="{REPO}/blob/main/{href}"'

    return re.sub(r'href="([^"]+)"', replace, content)


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "zh").mkdir(exist_ok=True)
    shutil.copy(ROOT / "web/style.css", OUT / "style.css")
    shutil.copy(ROOT / "web/social.png", OUT / "social.png")
    shutil.copy(ROOT / "web/home.js", OUT / "home.js")
    shutil.copytree(ROOT / "web/media", OUT / "media", dirs_exist_ok=True)
    shutil.copytree(
        ROOT / "web/brand",
        OUT / "brand",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("*.py"),
    )
    key = (ROOT / "web/indexnow-key.txt").read_text().strip()
    (OUT / (key + ".txt")).write_text(key)
    (OUT / "index.html").write_text(home())
    (OUT / "zh/index.html").write_text(home(True))
    for slug, (source, title) in PAGES.items():
        body = rewrite_links(
            markdown.markdown((ROOT / source).read_text(), extensions=["fenced_code", "tables"])
        )
        (OUT / (slug + ".html")).write_text(
            shell(
                title,
                title + " for Jev-native agent task scripts.",
                '<main class="doc">' + body + "</main>",
                slug + ".html",
            )
        )
    from apixly_jev_harness.task_cli import SPEC

    (OUT / "spec.json").write_text(json.dumps(SPEC, indent=2))
    shutil.copy(ROOT / "reports/acceptance.json", OUT / "acceptance.json")
    for report in (
        "parameter-prompt-ab.json",
        "parameter-ab.json",
        "evidence-progress-ab.json",
        "decision-diagnostics-ab.json",
        "tool-choice-offline-ab.json",
        "tool-choice-live-ab.json",
        "static-check-ab.json",
        "run-preflight-ab.json",
        "callback-contract-ab.json",
        "task-output-ab.json",
        "cli-arguments-ab.json",
    ):
        shutil.copy(ROOT / "reports" / report, OUT / report)
    (OUT / "social.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630"><rect width="1200" height="630" fill="#090d14"/><text x="90" y="140" fill="#a7efb1" font-family="sans-serif" font-size="32">JEV / HARNESS</text><text x="90" y="295" fill="#edf4f7" font-family="sans-serif" font-size="90">Give Jev the loop.</text><text x="90" y="385" fill="#9aaeba" font-family="sans-serif" font-size="30">Tools + parameters. Explicit context. Verified outcomes.</text></svg>'
    )
    urls = [BASE, BASE + "zh/"] + [BASE + slug + ".html" for slug in PAGES]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join("<url><loc>" + u + "</loc></url>" for u in urls)
        + "</urlset>"
    )
    (OUT / "llms.txt").write_text(
        "# Jev Harness\n\nIndependent Apixly community task runtime, not official TypeSafe AI software.\n\n"
        + "\n".join("- " + BASE + slug + ".html" for slug in PAGES)
        + "\n\nMachine contract: "
        + BASE
        + "spec.json\nEvidence: "
        + BASE
        + "acceptance.json\n"
    )
    (OUT / ".nojekyll").touch()
    print(
        "Built landing page, 5 documentation pages, Chinese overview, sitemap and machine contracts."
    )


if __name__ == "__main__":
    main()
