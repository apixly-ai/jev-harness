"""Build static, crawlable documentation and an evidence-bound landing page."""

import html
import json
import posixpath
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import markdown

from apixly_jev_harness import __version__ as VERSION

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site"
BASE = "https://apixly-ai.github.io/jev-harness/"
REPO = "https://github.com/apixly-ai/jev-harness"
PAGES = {
    "toolkits": {
        "en": (
            "docs/toolkits.md",
            "Jev Harness toolkits: thin scripts, evidence and MCP",
            "Reuse workspace, HTTP and Camofox source tools with short task scripts, including two 28-line examples. Read evidence progressively and connect the same task through MCP.",
        ),
        "zh-CN": (
            "docs/toolkits.zh-CN.md",
            "Jev Harness 工具包：薄脚本、证据与 MCP",
            "用薄任务脚本复用仓库、HTTP 与 Camofox 来源工具，查看两个 28 行示例，按需读取证据，并通过 MCP 接入同一任务。",
        ),
    },
    "agent-contract": {
        "en": (
            "docs/agent-contract.md",
            "Python agent task contract",
            "Install Jev Harness, define typed tools and parameter candidates, and run bounded Python tasks with explicit context and independent verification.",
        ),
        "zh-CN": (
            "docs/agent-contract.zh-CN.md",
            "Python 智能体任务协议",
            "安装 Jev Harness，定义类型化工具与参数候选，使用明确上下文和独立结果验证运行有边界的 Python 任务。",
        ),
    },
    "context": {
        "en": (
            "docs/context.md",
            "Context management for Jev agent loops",
            "How Jev Harness admits goals, facts, dialogue and tool results, preserves evidence references, and blocks repeated actions against unchanged state.",
        ),
        "zh-CN": (
            "docs/context.zh-CN.md",
            "Jev 智能体循环的上下文管理",
            "了解 Jev Harness 如何准入目标、事实、对话与工具结果，保留证据引用，并阻断相同状态下的重复动作。",
        ),
    },
    "adapters": {
        "en": (
            "docs/adapters.md",
            "Browser and desktop task adapters",
            "Connect bounded Jev Harness tasks to headless Camofox, macOS Accessibility or Windows UIA. Read permission, freshness and acceptance limits.",
        ),
        "zh-CN": (
            "docs/adapters.zh-CN.md",
            "浏览器与桌面任务适配器",
            "将有边界的 Jev Harness 任务连接到无头 Camofox、macOS Accessibility 或 Windows UIA，了解授权、新鲜度和验收范围。",
        ),
    },
    "architecture": {
        "en": (
            "docs/architecture.md",
            "Jev Harness architecture and design references",
            "How the primary AI, deterministic program, typed Jev decisions and independent verifier cooperate in Apixly’s Python task runtime.",
        ),
        "zh-CN": (
            "docs/architecture.zh-CN.md",
            "Jev Harness 架构与设计参考",
            "了解主 AI、确定性程序、类型化 Jev 决策和独立验证器如何在 Apixly 的 Python 任务运行时中协作。",
        ),
    },
    "evidence": {
        "en": (
            "reports/README.md",
            "Acceptance evidence and benchmark limits",
            "Inspect historical live synthetic browser acceptance, offline A/B reports, measured usage, negative results and unverified desktop completion.",
        ),
        "zh-CN": (
            "reports/README.zh-CN.md",
            "验收证据与评测范围",
            "复查历史真实合成浏览器验收、离线 A/B 报告、实测用量、负面结果，以及尚未验证的原生桌面完成状态。",
        ),
    },
    "faq": {
        "en": (
            "docs/faq.md",
            "Jev Harness FAQ: installation, tools and verification",
            "Answers about Apixly’s Jev Harness identity, exact Git installation, Jev Filter integration, typed choices, billing, browser evidence and execution limits.",
        ),
        "zh-CN": (
            "docs/faq.zh-CN.md",
            "Jev Harness 常见问题：安装、工具与验证",
            "了解 Apixly Jev Harness 的项目身份、准确 Git 安装方式、Jev Filter 集成、类型化候选、计费、浏览器证据和执行边界。",
        ),
    },
    "use-cases": {
        "en": (
            "docs/use-cases.md",
            "Jev Harness use cases: open research and investigation",
            "Design open research, repository diagnosis and controlled API investigation with AI-authored tools, dynamic Jev choices and independently checked artifacts. Acceptance status stays explicit.",
        ),
        "zh-CN": (
            "docs/use-cases.zh-CN.md",
            "Jev Harness 使用案例：开放调研与探索式诊断",
            "设计开放调研、仓库诊断与受控 API 排障，让 AI 编写工具、Jev 动态选择并独立核对产物，明确保留验收状态。",
        ),
    },
    "open-goals": {
        "en": (
            "docs/open-goals.md",
            "Open goals, dynamic tools and Jev delegation",
            "Give an AI an open goal, let it write task tools, and let Jev discover the route through dynamic tool and parameter choices. Inspect independent evidence and pending acceptance plans.",
        ),
        "zh-CN": (
            "docs/open-goals.zh-CN.md",
            "开放目标、动态工具与 Jev 托管",
            "给 AI 一个开放目标，让它编写任务工具，再由 Jev 通过动态工具与参数选择探索未知路径。复查独立证据与待完成的验收计划。",
        ),
    },
}


def language_paths(path):
    english = path.removeprefix("zh/")
    return english, "zh/" + english


def shell(title, description, body, path="", lang="en"):
    zh = lang == "zh-CN"
    prefix = "../" if zh else ""
    en_path, zh_path = language_paths(path)
    canonical = BASE + path
    title = title if "Jev Harness" in title else title + " · Jev Harness"
    alternates = "".join(
        f'<link rel="alternate" hreflang="{code}" href="{BASE}{target}">'
        for code, target in (("en", en_path), ("zh-CN", zh_path), ("x-default", en_path))
    )
    switch = prefix + (en_path or "index.html") if zh else zh_path
    image = BASE + ("brand/social.zh-CN.png" if zh else "social.png")
    graph = [
        {
            "@type": "Organization",
            "@id": BASE + "#maintainer",
            "name": "Apixly",
            "url": "https://github.com/apixly-ai",
        },
        {
            "@type": "SoftwareSourceCode",
            "@id": BASE + "#software",
            "name": "Jev Harness",
            "identifier": "apixly-jev-harness",
            "alternateName": "Apixly Jev Harness",
            "description": "Apixly’s Python runtime for open-goal tasks: an AI writes trusted tools and completion checks; Jev selects tools and dynamic parameter candidates from fresh observations in a bounded loop.",
            "codeRepository": REPO,
            "url": BASE,
            "programmingLanguage": "Python",
            "runtimePlatform": "Python 3.10+",
            "license": REPO + "/blob/main/LICENSE",
            "version": VERSION,
            "author": {"@id": BASE + "#maintainer"},
        },
        {
            "@type": "WebPage",
            "@id": canonical + "#webpage",
            "url": canonical,
            "name": title,
            "description": description,
            "inLanguage": lang,
            "about": {"@id": BASE + "#software"},
            "publisher": {"@id": BASE + "#maintainer"},
        },
    ]
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)
    labels = {
        "toolkits": "工具包" if zh else "Toolkits",
        "showcase": "演示案例" if zh else "Showcase",
        "open-goals": "开放目标" if zh else "Open goals",
        "contract": "任务协议" if zh else "Task contract",
        "faq": "常见问题" if zh else "FAQ",
        "evidence": "验收证据" if zh else "Evidence",
    }
    nav = "".join(
        f'<a href="{target}">{label}</a>'
        for target, label in (
            ("index.html#showcase", labels["showcase"]),
            ("toolkits.html", labels["toolkits"]),
            ("open-goals.html", labels["open-goals"]),
            ("agent-contract.html", labels["contract"]),
            ("faq.html", labels["faq"]),
            ("evidence.html", labels["evidence"]),
            (REPO, "GitHub ↗"),
        )
    )
    footer = (
        f"Apixly 独立社区项目 · v{VERSION}"
        if zh
        else f"Independent Apixly community project · v{VERSION}"
    )
    return f'''<!doctype html><html lang="{lang}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(description, quote=True)}">
<link rel="canonical" href="{canonical}">{alternates}
<meta property="og:title" content="{html.escape(title, quote=True)}"><meta property="og:description" content="{html.escape(description, quote=True)}"><meta property="og:url" content="{canonical}"><meta property="og:type" content="website"><meta property="og:image" content="{image}"><meta property="og:locale" content="{"zh_CN" if zh else "en_US"}"><meta property="og:locale:alternate" content="{"en_US" if zh else "zh_CN"}"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{html.escape(title, quote=True)}"><meta name="twitter:description" content="{html.escape(description, quote=True)}"><meta name="twitter:image" content="{image}">
<link rel="icon" type="image/svg+xml" href="{prefix}brand/icon.svg"><link rel="stylesheet" href="{prefix}style.css"><script type="application/ld+json">{data}</script></head><body>
<nav aria-label="{"主导航" if zh else "Main navigation"}"><a class="brand" href="index.html"><svg class="brand-glyph" viewBox="0 0 36 36" aria-hidden="true" fill="none"><path d="M5 14V5h12m-4-4 4 4-4 4M22 5h9v12m-4-4 4 4 4-4" stroke="#c6f67a" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M31 22v9H19m4-4-4 4 4 4M14 31H5V19m-4 4 4-4 4 4" stroke="#7de3e5" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg> jev<span> / harness</span></a>{nav}<a class="language-switch" href="{switch}" lang="{"en" if zh else "zh-CN"}" hreflang="{"en" if zh else "zh-CN"}">{"EN" if zh else "中文"}</a></nav>
{body}<footer><span>Jev Harness · MIT · {footer}</span><span><a href="{prefix}sitemap.xml">Sitemap</a> · <a href="{prefix}llms.txt">llms.txt</a></span></footer></body></html>'''


def home(zh=False):
    p = "../" if zh else ""

    def t(en, cn):
        return cn if zh else en

    def trace_row(number, label, detail, call=None):
        action = f"<code>{call}</code>" if call else ""
        return f'<div class="trace-row"><span class="trace-number">{number}</span><div><span class="room-label">{label}</span><p>{detail}</p>{action}</div></div>'

    icon = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 9V5h4M15 5h4v4M19 15v4h-4M9 19H5v-4M9 9h6v6H9z" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    lead = t(
        "Reuse source tools with a thin task script; our research and workspace examples each use 28 lines. Give Jev your goal, scope and completion check; it chooses the next tool and parameters as new evidence arrives. Connect the same task through MCP when needed.",
        "用薄脚本复用来源工具，调研与仓库示例各为 28 行。给 Jev 目标、范围与完成检查，由它根据新证据选择下一步工具和参数。需要时用 MCP 接入同一任务。",
    )
    install = f"pip install 'git+https://github.com/apixly-ai/jev-harness.git@v{VERSION}'"
    language = ".zh-CN" if zh else ""
    research_trace = "".join(
        (
            trace_row(
                "01",
                t("START WITH WHAT IS KNOWN", "从已知入口开始"),
                t(
                    "The script supplies starting pages and requirements. Jev discovers useful sources as it explores.",
                    "脚本提供起始页面与要求，Jev 在探索中发现有用的来源。",
                ),
                'inspect_page(page="starting-docs")',
            ),
            trace_row(
                "02",
                t("LET THE OBSERVATION OPEN THE ROUTE", "观察结果打开新路径"),
                t(
                    "A page reveals documentation and release links. Jev selects a newly observed link, then a relevant section.",
                    "页面返回文档与版本链接。Jev 选择刚发现的链接，再选择相关章节。",
                ),
                'follow_link(link_ref="observed-link-7")',
            ),
            trace_row(
                "03",
                t("FOLLOW THE EVIDENCE", "沿证据继续探索"),
                t(
                    "Jev can check a newer release, compare a second source, and record evidence against the task requirements.",
                    "Jev 可以查看较新版本、比较另一来源，并按任务要求记录证据。",
                ),
                'record_evidence(source_ref="release-section", field="offline_support")',
            ),
        )
    )
    repository_trace = "".join(
        (
            trace_row(
                "01",
                t("OBSERVE THE FAILURE", "观察失败现场"),
                t(
                    "The script supplies a repository snapshot and an installed-package failure. Jev follows the evidence to locate the cause.",
                    "脚本提供仓库快照和安装包失败现象，Jev 沿着证据定位原因。",
                ),
                'read_artifact(artifact_ref="wheel-failure")',
            ),
            trace_row(
                "02",
                t("CHOOSE WHAT TO INSPECT", "选择下一份线索"),
                t(
                    "Jev chooses among newly observed source files, package contents and existing check records.",
                    "Jev 从刚观察到的源文件、包内容和已有检查记录中选择。",
                ),
                'inspect_package(entry_ref="observed-module")',
            ),
            trace_row(
                "03",
                t("TEST THE EXPLANATION", "验证解释"),
                t(
                    "A recorded check contradicts the hypothesis. Jev can inspect another artifact or source relationship.",
                    "已有检查记录与假设不符。Jev 可以继续查看另一份产物或源码关系。",
                ),
                'read_artifact(artifact_ref="installed-import-result")',
            ),
        )
    )
    api_trace = "".join(
        (
            trace_row(
                "01",
                t("INSPECT A SYNTHETIC FAILURE", "检查合成故障"),
                t(
                    "The script supplies a synthetic task entry and read-only status, schema and event tools.",
                    "脚本提供合成任务入口，以及只读状态、schema 和事件工具。",
                ),
                'read_status(task_ref="synthetic-17")',
            ),
            trace_row(
                "02",
                t("FOLLOW A NEW DEPENDENCY", "跟随新发现的依赖"),
                t(
                    "The response reveals a dependency. Jev chooses which observed resource and event page to read next.",
                    "响应揭示一个依赖。Jev 选择接下来读取哪个已观察资源和事件页。",
                ),
                'read_events(resource_ref="observed-dependency-2", page="observed-1")',
            ),
            trace_row(
                "03",
                t("CHECK THE SOURCE CONTRACT", "核对来源契约"),
                t(
                    "Jev reads the source contract, compares it with status and events, and records a source-linked diagnosis.",
                    "Jev 读取来源契约，对照状态与事件，记录带来源的诊断。",
                ),
                'read_schema(schema_ref="observed-state-contract")',
            ),
        )
    )
    body = f'''
<main class="wrap home">
  <section class="hero" aria-labelledby="hero-title">
    <div class="hero-copy">
      <div class="eyebrow"><span class="status-dot"></span> {t("OPEN GOALS. AI-AUTHORED TOOLS. A JEV LOOP.", "开放目标 · AI 编写工具 · JEV 托管循环")}</div>
      <h1 id="hero-title">{t("Give AI a goal.<br><em>Let Jev find<br>the next step.</em>", "把目标交给 AI，<br><em>把探索过程<br>交给 Jev。</em>")}</h1>
      <p class="hero-lead">{lead}</p>
      <div class="actions"><a class="button" href="{p}toolkits.html">{t("Use the toolkits", "使用通用工具包")} <span aria-hidden="true">↗</span></a><a class="button secondary" href="#start">{t("Give your AI the contract", "把协议交给 AI")} <span aria-hidden="true">→</span></a></div>
      <div class="hero-meta"><span>Python 3.10+</span><span>MIT</span><span>v{VERSION}</span></div>
      <p class="entity-note">{t("An independent Apixly Python runtime for AI-authored task scripts, dynamic tool choices and checked outcomes.", "Apixly 的独立 Python 运行时，连接 AI 编写的任务脚本、动态工具选择与结果核对。")}</p>
    </div>
    <div class="control-room" role="img" aria-label="{t("Open research task example: AI defines tools; Jev chooses a newly observed link and section; code checks a source-linked output.", "开放调研任务示例：AI 定义工具，Jev 选择刚发现的链接和章节，程序核对带来源的输出。")}">
      <div class="room-head"><span>{icon} TASK CONTROL ROOM</span><span class="mini-badge">{t("TASK CONTRACT", "任务契约")}</span></div>
      <div class="goal-line"><span class="room-label">{t("OPEN GOAL", "开放目标")}</span><strong>{t("Find suitable tools. Save a sourced comparison.", "找到符合要求的工具，保存带来源的比较。")}</strong></div>
      <div class="room-workspace">
        <div class="context-stack"><div class="room-label">{t("FRESH OBSERVATION", "最新观察")}</div><div class="context-line"><span>{t("new links", "新链接")}</span><b>7</b></div><div class="context-line"><span>{t("evidence", "证据")}</span><b class="cyan">updating</b></div><div class="context-line"><span>{t("next route", "下一条路径")}</span><b class="cyan">Jev →</b></div><div class="room-label context-note">{t("TOOLS DEFINED BY AI", "AI 定义的工具")}</div><div class="tool-option">inspect_page</div><div class="tool-option chosen">follow_link <span>← Jev</span></div><div class="tool-option">read_evidence</div><div class="tool-option">record_evidence</div></div>
        <div class="decision-column"><div class="decision-core">{icon}<strong>Jev</strong><small>{t("chooses from current evidence", "依据当前证据选择")}</small></div><div class="bound-call"><span class="room-label">{t("DYNAMIC PARAMETER CHOICE", "动态参数选择")}</span><code>follow_link(<br> link_ref=<b>"observed-7"</b>)</code></div></div>
      </div>
      <div class="verify-line"><span class="check-mark">↻</span><div><strong>{t("New evidence. A new decision.", "新证据，带来下一次判断。")}</strong><small>{t("Stop when the output passes its independent check.", "输出通过独立检查，才确认完成。")}</small></div><span class="verify-pulse"></span></div>
      <div class="loop-rail" aria-hidden="true"><span>{t("Observe", "观察")}</span><span>{t("Choose", "选择")}</span><span>{t("Execute", "执行")}</span><span>{t("Check / repeat", "检查 / 继续")}</span></div>
    </div>
  </section>
  <div class="principle-strip"><span>{t("BOUND THE EFFECTS. DISCOVER THE ROUTE.", "限定操作范围，探索执行路径。")}</span><p>{t("Fresh observations", "最新观察")}<i> / </i>{t("Dynamic candidates", "动态候选")}<i> / </i>{t("Checkable artifacts", "可核对产物")}</p><button class="motion-control" type="button" aria-pressed="false" data-pause="{t("Pause motion", "暂停动画")}" data-resume="{t("Resume motion", "播放动画")}" hidden>{t("Pause motion", "暂停动画")}</button></div>
  <div class="ownership-grid" aria-label="{t("Who owns each responsibility", "职责分工")}"><div><span class="room-label">PRIMARY AI</span><strong>{t("Defines the task script", "定义任务脚本")}</strong><p>{t("Goal, tools, candidate providers and independent completion checks.", "目标、工具、候选提供器与独立完成检查。")}</p></div><div><span class="room-label">JEV</span><strong>{t("Chooses the next move", "选择下一步行动")}</strong><p>{t("Uses current context to select tools and meaningful parameter candidates.", "依据当前上下文选择工具和有意义的参数候选。")}</p></div><div><span class="room-label">TRUSTED CODE</span><strong>{t("Executes and checks", "执行并核对结果")}</strong><p>{t("Collects observations, binds real values, applies limits and verifies artifacts.", "采集观察、绑定实际值、落实边界并验证产物。")}</p></div></div>
  <section class="section showcase" id="showcase" aria-labelledby="showcase-title">
    <div class="section-heading"><div><div class="eyebrow">01 / {t("DESIGN FOR OPEN TASKS", "围绕开放任务设计")}</div><h2 id="showcase-title">{t("Write the tools.<br>Discover the path.", "先定义能力，<br>再探索路径。")}</h2></div><p>{t("Three task examples show how to define capabilities once and let each observation guide the next tool call. Explore the goal, tools and output contract.", "三个任务示例展示：先定义能力，再让每次观察引导下一次工具调用。查看目标、工具与产物契约。")}</p></div>
    <div class="case-tabs" role="tablist" aria-label="{t("Open task designs", "开放任务设计")}" hidden><button type="button" role="tab" id="tab-browser" aria-controls="case-browser" aria-selected="true" tabindex="0"><span>01</span>{t("Open research", "开放调研")}</button><button type="button" role="tab" id="tab-python" aria-controls="case-python" aria-selected="false" tabindex="-1"><span>02</span>{t("Repository diagnosis", "仓库诊断")}</button><button type="button" role="tab" id="tab-guards" aria-controls="case-guards" aria-selected="false" tabindex="-1"><span>03</span>{t("API investigation", "API 排障")}</button></div>
    <article class="case-panel" id="case-browser" role="tabpanel" aria-labelledby="tab-browser">
      <div class="trace-demo"><div class="frame-top"><span class="window-dots"><i></i><i></i><i></i></span><span>research_task.py / {t("example tool calls", "工具调用示例")}</span><span class="frame-badge">{t("TASK EXAMPLE", "任务示例")}</span></div><div class="trace-steps">{research_trace}</div><div class="artifact-preview"><span class="room-label">{t("OUTPUT CONTRACT", "产物契约")}</span><strong>comparison.json + source references</strong><p>{t("Reopen the comparison and check three distinct tools, each requirement and its supporting sources.", "重新打开比较，核对三个不同工具、每项约束及其来源依据。")}</p></div></div>
      <div class="case-copy"><div class="case-kicker">{t("OPEN RESEARCH / TASK DESIGN", "开放调研 / 任务设计")}</div><h3>{t("Start with a question.<br>Find the useful sources.", "从问题出发，<br>找到有用的来源。")}</h3><p>{t("Find three self-hosted tools that meet given constraints and save a sourced comparison. Which pages, sections and versions matter is discovered during the run.", "找到三款符合指定条件的自托管工具，保存带来源的比较。相关页面、章节和版本在执行中发现。")}</p><dl class="case-details"><div><dt>{t("AI WRITES", "AI 编写")}</dt><dd>{t("Browser tools, dynamic link/section candidates, evidence recorder, artifact check.", "浏览工具、动态链接与章节候选、证据记录器、产物检查。")}</dd></div><div><dt>{t("JEV CHOOSES", "JEV 选择")}</dt><dd>{t("Next page → section → evidence field → whether more evidence is needed.", "下一页 → 章节 → 证据字段 → 是否继续收集。")}</dd></div><div><dt>{t("BOUND / CHECK", "边界 / 检查")}</dt><dd>{t("Allowed origins and steps; independently verify three tools, all requirements and cited sources.", "允许来源与步数；独立核对三个工具、全部约束与引用来源。")}</dd></div></dl><a class="text-link" href="{p}use-cases.html">{t("Read the open-task design", "查看开放任务设计")} ↗</a><p class="case-footnote">{t("Extend the task with a registered trusted generator for search terms or prose. Jev can select that tool and continue using its returned candidates.", "可注册可信生成工具，扩展搜索词或文稿能力。Jev 选择调用该工具，再利用返回的候选继续探索。")}</p></div>
    </article>
    <article class="case-panel" id="case-python" role="tabpanel" aria-labelledby="tab-python" hidden>
      <div class="trace-demo"><div class="frame-top"><span class="window-dots"><i></i><i></i><i></i></span><span>diagnose_repo.py / {t("example tool calls", "工具调用示例")}</span><span class="frame-badge">{t("TASK EXAMPLE", "任务示例")}</span></div><div class="trace-steps">{repository_trace}</div><div class="artifact-preview"><span class="room-label">{t("OUTPUT CONTRACT", "产物契约")}</span><strong>diagnosis.json + source checks</strong><p>{t("Check that the saved diagnosis links the recorded failure to captured source revisions and artifacts.", "核对已保存诊断是否把已有失败记录关联到采集的代码版本与产物。")}</p></div></div>
      <div class="case-copy"><div class="case-kicker">{t("REPOSITORY / TASK DESIGN", "仓库 / 任务设计")}</div><h3>{t("Follow the failure.<br>Find the cause.", "跟随失败线索，<br>找到问题原因。")}</h3><p>{t("Investigate why recorded repository tests passed while an installed package failed. Read files and existing artifacts, then save a diagnosis supported by those sources.", "调查已有记录中为什么仓库测试通过，安装包却失败。读取文件与已有产物，保存有来源依据的诊断。")}</p><dl class="case-details"><div><dt>{t("AI WRITES", "AI 编写")}</dt><dd>{t("Read-only repository tools, existing failure artifacts and source checks.", "仓库只读工具、已有失败产物与来源核验。")}</dd></div><div><dt>{t("JEV CHOOSES", "JEV 选择")}</dt><dd>{t("Which file, artifact or source relationship to inspect after each result.", "根据每次结果，选择下一份文件、产物或源码关系。")}</dd></div><div><dt>{t("BOUND / CHECK", "边界 / 检查")}</dt><dd>{t("Permitted snapshot and artifacts; verify saved references and evidence.", "获准的快照与产物；核对保存的引用和依据。")}</dd></div></dl><a class="text-link" href="{p}use-cases.html">{t("Read the diagnosis design", "查看诊断任务设计")} ↗</a><p class="case-footnote">{t("Use read-only tools to connect failure artifacts with source evidence. Save the diagnosis as a separate artifact.", "使用只读工具关联失败产物与源码证据，将诊断保存为独立产物。")}</p></div>
    </article>
    <article class="case-panel" id="case-guards" role="tabpanel" aria-labelledby="tab-guards" hidden>
      <div class="trace-demo"><div class="frame-top"><span class="window-dots"><i></i><i></i><i></i></span><span>investigate_api.py / {t("example tool calls", "工具调用示例")}</span><span class="frame-badge">{t("TASK EXAMPLE", "任务示例")}</span></div><div class="trace-steps">{api_trace}</div><div class="artifact-preview"><span class="room-label">{t("OUTPUT CONTRACT", "产物契约")}</span><strong>incident-evidence.json + source state checks</strong><p>{t("Save source state and diagnostic evidence, then independently check the diagnosis against those sources.", "保存来源状态与诊断依据，再对照这些来源独立核对诊断。")}</p></div></div>
      <div class="case-copy"><div class="case-kicker">{t("CONTROLLED API / TASK DESIGN", "受控 API / 任务设计")}</div><h3>{t("Follow the response.<br>Map the dependencies.", "跟随响应线索，<br>理清任务依赖。")}</h3><p>{t("Investigate a synthetic task through a read-only API. Status, event pages and newly discovered dependencies guide the next choice.", "通过只读 API 调查合成环境中的任务。状态、事件页与新发现的依赖引导下一步选择。")}</p><dl class="case-details"><div><dt>{t("AI WRITES", "AI 编写")}</dt><dd>{t("Allowed API scope, resource readers, recorded events and independent source checks.", "允许的 API 范围、资源读取器、已有事件与独立来源核验。")}</dd></div><div><dt>{t("JEV CHOOSES", "JEV 选择")}</dt><dd>{t("Which observed resource, dependency or event page to inspect next.", "下一步查看哪个已观察资源、依赖或事件页。")}</dd></div><div><dt>{t("BOUND / CHECK", "边界 / 检查")}</dt><dd>{t("Read-only tools and request limits; recheck source state and the saved evidence.", "只读工具与请求限制；回查来源状态和保存的证据。")}</dd></div></dl><a class="text-link" href="{p}use-cases.html">{t("Read the API investigation design", "查看 API 排障设计")} ↗</a><p class="case-footnote">{t("Read-only resource investigation, with a source-linked diagnosis saved as the task artifact.", "通过只读资源调查，把带来源的诊断保存为任务产物。")}</p></div>
    </article>
  </section>
  <section class="section how" id="how" aria-labelledby="how-title"><div class="section-heading"><div><div class="eyebrow">02 / {t("FROM INTENT TO EXECUTION", "从目标到执行")}</div><h2 id="how-title">{t("One task contract.<br>Many possible routes.", "一份任务契约，<br>多条可能路径。")}</h2></div><a class="text-link" href="{p}architecture.html">{t("Explore the architecture", "查看架构")} ↗</a></div><div class="loop"><div><small>01 / AUTHOR</small><strong>{t("AI writes the capability", "AI 编写任务能力")}</strong><p>{t("Tools, candidate providers, observations and an independent check.", "定义工具、候选提供器、观察与独立检查。")}</p></div><div><small>02 / OBSERVE</small><strong>{t("Bring fresh context", "取得最新上下文")}</strong><p>{t("Goal, state, admitted evidence and action history guide the next decision.", "目标、状态、准入证据与执行历史引导下一轮判断。")}</p></div><div><small>03 / CHOOSE + ACT</small><strong>{t("Jev chooses; code acts", "Jev 选择，程序执行")}</strong><p>{t("Select registered tools and current candidates. Bind, check and execute real values.", "选择注册工具和当前候选，程序绑定、检查并执行实际值。")}</p></div><div><small>04 / CHECK + LOOP</small><strong>{t("Continue or return evidence", "继续探索或返回证据")}</strong><p>{t("Verify the outcome. Repeat with new observations, or finish, block or request review.", "验证结果，带着新观察继续，或完成、阻塞、请求复核。")}</p></div></div></section>
  <section class="section capabilities"><div class="capability-intro"><div class="eyebrow">03 / {t("A REUSABLE TOOL FOUNDATION", "可复用的工具底座")}</div><h2>{t("New task.<br>Same loop.", "任务可以变，<br>循环可复用。")}</h2><p>{t("Reuse WorkspaceTools, WebTools and EvidenceTask. Add your scope and source checks; the runtime manages the loop and evidence report.", "复用 WorkspaceTools、WebTools 和 EvidenceTask，加入任务范围和来源检查，由运行时管理循环和证据报告。")}</p><a class="text-link" href="{p}toolkits.html">{t("Explore the toolkits", "查看工具包")} ↗</a></div><div class="capability-grid"><article class="card"><div class="feature-icon">{{ }}</div><h3>{t("Candidates can appear later", "候选可以运行后才出现")}</h3><p>{t("Dynamic domains come from new observations. Dependent parameters resolve in order.", "从新观察生成动态候选，依赖参数按顺序解析。")}</p></article><article class="card"><div class="feature-icon">↳</div><h3>{t("Each result informs the next step", "每次结果推动下一步")}</h3><p>{t("Admit result summaries and action history; task tools can read retained evidence.", "准入结果摘要与操作历史，由任务工具读取保留的证据。")}</p></article><article class="card"><div class="feature-icon">&gt;_</div><h3>{t("An interface your AI can use", "AI 可以直接使用的接口")}</h3><p>{t("Toolkit scaffolds, machine-readable task contracts and optional MCP access.", "工具包模板、机器可读任务契约，以及按需 MCP 接入。")}</p></article><article class="card"><div class="feature-icon">◎</div><h3>{t("Completion comes with evidence", "完成需要附带证据")}</h3><p>{t("Independent checks, action history and model-usage records in one ledger.", "独立检查、操作历史和模型用量记录保存在同一账本中。")}</p></article></div></section>
  <section class="section historical-evidence" id="browser-evidence" aria-labelledby="evidence-title"><div class="section-heading"><div><div class="eyebrow">04 / {t("THE EXECUTION LOOP IN ACTION", "执行循环的真实验收")}</div><h2 id="evidence-title">{t("See the loop<br>inside a browser.", "在浏览器中，<br>看清完整循环。")}</h2></div><p>{t("A historical four-step browser fixture connects observation, Jev selection, execution and independent result checks.", "历史四步浏览器夹具串起观察、Jev 选择、执行与独立结果检查。")}</p></div><div class="case-panel"><div class="demo-frame"><div class="frame-top"><span class="window-dots"><i></i><i></i><i></i></span><span>travel-request / local fixture</span><span class="frame-badge">{t("SCREENSHOT REPLAY", "截图回放")}</span></div><video id="browser-video" controls loop muted playsinline preload="none" poster="{p}media/browser-poster{language}.webp" aria-label="{t("Screenshot replay of the historical synthetic browser travel-draft fixture", "历史合成浏览器旅行草稿夹具的截图回放")}"><source src="{p}media/browser-demo{language}.mp4" type="video/mp4"><a href="{p}media/browser-demo{language}.mp4">{t("Download the replay", "下载回放")}</a></video><div class="media-caption">{t("Screenshot replay of the local browser fixture. Follow the evidence link to inspect the Jev acceptance record.", "本地浏览器夹具的截图回放。通过证据链接查看 Jev 验收记录。")}</div></div><div class="case-copy"><div class="case-kicker">{t("v0.1.0 / HISTORICAL LIVE ACCEPTANCE", "v0.1.0 / 历史真实验收")}</div><h3>{t("A four-step browser task.<br>Independently checked.", "四步浏览器任务，<br>结果独立核对。")}</h3><p>{t("Real Jev + headless Camofox filled traveler and destination, set flexible dates and prepared a draft. The verifier checked field values and final DOM text.", "真实 Jev + 无头 Camofox 填写旅客和目的地、设置灵活日期并生成草稿。验证器回读字段值与最终 DOM 文字。")}</p><dl class="case-details"><div><dt>{t("OBSERVED RESULT", "已验证结果")}</dt><dd>Draft ready: Mira | London | flexible=true</dd></div><div><dt>{t("SCOPE", "范围")}</dt><dd>{t("4 tool executions in a local synthetic travel-draft fixture.", "本地合成旅行草稿夹具，4 次工具执行。")}</dd></div></dl><a class="text-link" href="{p}evidence.html">{t("Inspect the historical evidence", "复查历史验收证据")} ↗</a></div></div></section>
  <section class="evidence-band"><div class="evidence-icon">↗</div><div><div class="eyebrow">{t("BUILD YOUR OWN TOOLCHAIN", "构建自己的工具链")}</div><h3>{t("Add capabilities. Reuse the loop.", "扩展任务能力，复用同一循环。")}</h3><p>{t("Define tools around your workflow, return meaningful candidates from fresh observations, and give every task a completion check. The same runtime connects them into a Jev agent loop.", "围绕你的工作定义工具，从最新观察返回有意义的候选，再为每项任务定义完成检查。同一个运行时将它们连接成 Jev 智能体循环。")}</p></div><a class="button secondary" href="{p}evidence.html">{t("Read the evidence", "查看验收记录")} ↗</a></section>
  <section class="section start" id="start" aria-labelledby="start-title"><div class="start-copy"><div class="eyebrow">05 / {t("GIVE YOUR AI THE CONTRACT", "把协议交给 AI")}</div><h2 id="start-title">{t("Reuse the toolkit.<br>Add your task contract.", "复用工具包，<br>补上任务契约。")}</h2><p>{t("Start with the workspace toolkit or the 28-line research example. Define permitted sources and quote categories, inspect the task contract, then let Jev explore and save an independently checked artifact.", "从仓库工具包或 28 行调研示例开始，定义允许来源和引用类别，查看任务契约，再由 Jev 探索并保存独立核验的产物。")}</p><div class="actions"><a class="text-link" href="{p}toolkits.html">{t("Toolkits & thin scripts", "工具包与薄脚本")} ↗</a><a class="text-link" href="{p}spec.json">spec.json ↗</a><a class="text-link" href="{p}toolkit-live-2026-10-11.json">{t("Inspect toolkit acceptance", "查看工具包验收")} ↗</a></div><p class="small">{t("Runtime inputs choose the source root and output. Add MCP when a primary agent needs to inspect or operate the same capabilities; source and model usage stay explicit in the evidence ledger.", "运行时输入决定来源 root 和输出位置。主 AI 需要查看或操作同一能力时再接入 MCP，来源与模型用量保留在验收账本中。")}</p></div><div class="editor"><div class="editor-head"><span>{t("terminal / toolkit scaffold", "terminal / 工具包模板")}</span><button class="copy-button" type="button" data-copy="{html.escape(install, quote=True)}" data-copied="{t("Copied", "已复制")}" hidden>{t("Copy install", "复制安装命令")}</button></div><pre><span class="code-muted"># {t("Create a virtual environment", "创建虚拟环境")}</span>
python -m venv .venv
. .venv/bin/activate

<span class="code-muted"># {t("Install the pinned version", "安装固定版本")}</span>
{html.escape(install)}

jev-harness <b>quickstart</b>
jev-harness <b>init-task</b> task.py --toolkit workspace
jev-harness <b>check-task</b> task.py
<span class="code-muted"># {t("Configure TYPESAFE_API_KEY in your environment", "在环境中配置 TYPESAFE_API_KEY")}</span>
jev-harness <b>run</b> task.py --goal "Investigate source evidence" --inputs '{{
  "root":"permitted-corpus",
  "markers":{{"finding":"source marker"}},
  "output":"local-results/report.json"
}}'</pre></div></section>
  <section class="section questions" aria-labelledby="questions-title"><div class="section-heading"><div><div class="eyebrow">06 / {t("FIND YOUR ANSWER", "找到需要的答案")}</div><h2 id="questions-title">{t("Understand the contract.<br>Inspect the evidence.", "读懂任务契约，<br>复查验收证据。")}</h2></div></div><div class="question-links"><a href="{p}faq.html"><strong>{t("How does AI hand off an open task?", "AI 如何托管开放任务？")} ↗</strong><small>{t("Script ownership, dynamic candidates, generated content and task contracts.", "脚本职责、动态候选、生成内容与任务契约。")}</small></a><a href="{p}use-cases.html"><strong>{t("Which cases show the core idea?", "哪些案例突出核心思路？")} ↗</strong><small>{t("Open research, repository diagnosis and controlled API investigation: goals, tools and output contracts.", "开放调研、仓库诊断与受控 API 排障：目标、工具与产物契约。")}</small></a></div></section>
  <section class="related"><span>{t("PART OF YOUR TOOLKIT", "工具箱里的其他项目")}</span><a href="https://apixly-ai.github.io/jev-filter/"><b>Jev Filter</b><small>{t("Find the signal in many records", "从多条记录中筛选信号")}</small>↗</a><a href="https://github.com/JIA-ss/ai-remote"><b>ai-remote</b><small>{t("MCP access to your computers", "通过 MCP 访问你的电脑")}</small>↗</a></section>
</main><script src="{p}home.js" defer></script>'''
    for slug in PAGES:
        body = body.replace(f'href="{p}{slug}.html"', f'href="{slug}.html"')
    return shell(
        t(
            "Jev Harness: AI-authored tools for open-goal agent loops",
            "Jev Harness：AI 编写工具，Jev 托管开放目标的智能体循环",
        ),
        lead,
        body,
        "zh/" if zh else "",
        "zh-CN" if zh else "en",
    )


def rewrite_links(content, zh=False, source="docs/agent-contract.md"):
    prefix = "../" if zh else ""
    page_sources = {
        str(Path(file).as_posix()): slug + ".html"
        for slug, variants in PAGES.items()
        for file, _, _ in variants.values()
    }
    report_names = {file.name for file in (ROOT / "reports").glob("*.json")}

    def replace(match):
        attribute, href = match.groups()
        if href.startswith(("http:", "https:", "#", "mailto:", "data:")):
            return match.group(0)
        parts = urlsplit(html.unescape(href))
        normalized = posixpath.normpath(posixpath.join(str(Path(source).parent), parts.path))
        filename = Path(parts.path).name
        if normalized in page_sources:
            target = page_sources[normalized]
        elif filename in report_names or filename == "spec.json":
            target = prefix + filename
        elif normalized in ("README.md", "README.zh-CN.md"):
            target = "index.html"
        elif normalized.startswith("web/media/"):
            target = prefix + "media/" + normalized.removeprefix("web/media/")
        elif normalized.startswith("web/brand/"):
            target = prefix + "brand/" + normalized.removeprefix("web/brand/")
        else:
            target = REPO + "/blob/main/" + normalized
        if parts.fragment:
            target += "#" + parts.fragment
        return f'{attribute}="{html.escape(target, quote=True)}"'

    rewritten = re.sub(r'(href|src|poster)="([^"]+)"', replace, content)

    def language_switch(match):
        start, target, end, label = match.groups()
        if urlsplit(target).scheme or not target.endswith(".html"):
            return match.group(0)
        if label == "English":
            target = ("../" if zh else "") + target
        else:
            target = ("" if zh else "zh/") + target
        return start + target + end + label + "</a>"

    return re.sub(
        r'(<a\b[^>]*href=")([^"]+)("[^>]*>)(English|简体中文|中文)</a>',
        language_switch,
        rewritten,
    )


def document(source, title, description, slug, zh=False):
    language = "zh-CN" if zh else "en"
    content = markdown.markdown(
        (ROOT / source).read_text(encoding="utf-8"), extensions=["fenced_code", "tables", "toc"]
    )
    links = "".join(
        f'<a href="{name}.html"'
        + (' aria-current="page"' if name == slug else "")
        + ">"
        + html.escape(variants[language][1])
        + "</a>"
        for name, variants in PAGES.items()
    )
    body = (
        '<main class="doc"><div class="doc-breadcrumb"><a href="index.html">Jev Harness</a>'
        + " / "
        + html.escape(title)
        + '</div><nav class="doc-links" aria-label="'
        + ("文档导航" if zh else "Documentation")
        + '">'
        + links
        + "</nav>"
        + rewrite_links(content, zh=zh, source=source)
        + '<p class="doc-source"><a href="'
        + REPO
        + "/blob/main/"
        + source
        + '">'
        + ("在 GitHub 查看本文源码" if zh else "View this page’s source on GitHub")
        + " ↗</a></p></main>"
    )
    return shell(title, description, body, ("zh/" if zh else "") + slug + ".html", language)


def discovery_files():
    pairs = [("", "zh/")] + [(slug + ".html", "zh/" + slug + ".html") for slug in PAGES]
    urls = [BASE + path for pair in pairs for path in pair]
    entries = []
    for english, chinese in pairs:
        links = "".join(
            f'<xhtml:link rel="alternate" hreflang="{lang}" href="{BASE}{path}"/>'
            for lang, path in (("en", english), ("zh-CN", chinese), ("x-default", english))
        )
        entries.extend(f"<url><loc>{BASE}{path}</loc>{links}</url>" for path in (english, chinese))
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">'
        + "".join(entries)
        + "</urlset>\n",
        encoding="utf-8",
        newline="\n",
    )
    (OUT / "sitemap.txt").write_text("\n".join(urls) + "\n", encoding="utf-8", newline="\n")
    sections = [
        "# Jev Harness",
        "Apixly’s independent MIT Python runtime for open goals through reusable toolkits, thin scripts and Jev agent loops. Not an official TypeSafe AI product.",
        f"Distribution: apixly-jev-harness. Python namespace: apixly_jev_harness. CLI: jev-harness / apixly-jev-harness. Version: {VERSION}.",
        f"Install: pip install 'git+{REPO}.git@v{VERSION}'. The PyPI name jev-harness belongs to an unrelated project.",
        "Programs provide registered tools and parameter candidates, execute effects and independently verify completion. Jev selects supplied references. Inference is billable; unknown usage remains unknown. No general success or savings guarantee.",
        "Historical browser acceptance uses a local synthetic fixture. Homepage media is a zero-inference screenshot replay. Native desktop completion remains unverified.",
        "## English",
        f"- [Homepage]({BASE}): Jev Harness identity, visual cases and installation.",
    ]
    sections.extend(
        f"- [{variants['en'][1]}]({BASE}{slug}.html): {variants['en'][2]}"
        for slug, variants in PAGES.items()
    )
    sections += [
        "## 简体中文",
        f"- [中文主页]({BASE}zh/): Jev Harness 项目介绍、演示案例和安装入口。",
    ]
    sections.extend(
        f"- [{variants['zh-CN'][1]}]({BASE}zh/{slug}.html): {variants['zh-CN'][2]}"
        for slug, variants in PAGES.items()
    )
    sections += [
        "## Machine-readable evidence",
        f"- [Task spec]({BASE}spec.json)",
        f"- [Historical acceptance]({BASE}acceptance.json)",
        f"- [Toolkit live acceptance]({BASE}toolkit-live-2026-10-11.json)",
        f"- [Toolkit source fixtures]({BASE}toolkit-fixtures.json)",
        f"- [Toolkit protocol A/B]({BASE}toolkit-protocol-ab.json)",
        f"- [Media provenance]({BASE}media/showcase.json)",
        f"- [Repository]({REPO})",
    ]
    (OUT / "llms.txt").write_text("\n\n".join(sections) + "\n", encoding="utf-8", newline="\n")
    return len(urls)


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
    key = (ROOT / "web/indexnow-key.txt").read_text(encoding="utf-8").strip()
    (OUT / (key + ".txt")).write_text(key, encoding="utf-8", newline="\n")
    (OUT / "index.html").write_text(home(), encoding="utf-8", newline="\n")
    (OUT / "zh/index.html").write_text(home(True), encoding="utf-8", newline="\n")
    for slug, variants in PAGES.items():
        for language, (source, title, description) in variants.items():
            zh = language == "zh-CN"
            target = OUT / ("zh" if zh else "") / (slug + ".html")
            target.write_text(
                document(source, title, description, slug, zh), encoding="utf-8", newline="\n"
            )
    from apixly_jev_harness.task_cli import SPEC

    (OUT / "spec.json").write_text(json.dumps(SPEC, indent=2), encoding="utf-8", newline="\n")
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
        "context-budget-ab.json",
        "planning-diagnostics-ab.json",
        "execution-identity-ab.json",
        "transport-counters-ab.json",
        "provider-signature-ab.json",
        "verification-types-ab.json",
        "parameter-snapshots-ab.json",
        "candidate-budget-ab.json",
        "action-identity-ab.json",
        "toolkit-live-2026-10-11.json",
        "toolkit-fixtures.json",
        "toolkit-protocol-ab.json",
        "lazy-delegation-live.json",
        "delegation-lifecycle-ab.json",
        "geo-bilingual-2026-10-11.json",
        "browser-cold-2026-10-12.json",
        "delegation-2026-10-12.json",
    ):
        shutil.copy(ROOT / "reports" / report, OUT / report)
    shutil.copy(ROOT / "web/brand/social.svg", OUT / "social.svg")
    count = discovery_files()
    (OUT / ".nojekyll").touch()
    print(f"Built {count} bilingual pages, sitemap, evidence and machine contracts.")


if __name__ == "__main__":
    main()
