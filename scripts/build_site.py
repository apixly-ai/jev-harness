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
    page = f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)} · Jev Harness</title><meta name="description" content="{html.escape(description, quote=True)}"><link rel="canonical" href="{canonical}">{alternate}<meta property="og:title" content="{html.escape(title, quote=True)}"><meta property="og:description" content="{html.escape(description, quote=True)}"><meta property="og:url" content="{canonical}"><meta property="og:type" content="website"><meta property="og:image" content="{BASE}social.png"><link rel="stylesheet" href="{prefix}style.css"><script type="application/ld+json">{json.dumps(data)}</script></head><body><nav><a class="brand" href="{prefix}index.html">jev<span> / harness</span></a><a href="{prefix}agent-contract.html">Agent contract</a><a href="{prefix}context.html">Context</a><a href="{prefix}evidence.html">Evidence</a><a href="{REPO}">GitHub ↗</a><a href="{prefix}{"index.html" if lang == "zh-CN" else "zh/"}">{"EN" if lang == "zh-CN" else "中文"}</a></nav>{body}<footer><span>Jev Harness · Apixly independent community project · MIT</span><span>Not an official TypeSafe AI product. Early {VERSION}.</span></footer></body></html>'''
    if lang == "zh-CN":
        for old, new in [
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
    h = "让 Jev<br>拥有<em>执行循环。</em>" if zh else "Give Jev<br><em>the loop.</em>"
    lead = (
        "AI 定义任务、工具与参数候选。Jev 选择下一步，程序执行并验证结果。"
        if zh
        else "AI defines the task, tools and parameter candidates. Jev chooses the next step. Your code executes and verifies the outcome."
    )
    body = f'''<main class="wrap"><section class="hero"><div><div class="eyebrow">Jev native / AI native / Python</div><h1>{h}</h1><p>{lead}</p><div class="actions"><a class="button" href="{p}agent-contract.html">{"开始编写任务" if zh else "Build your first task"} →</a><a class="button secondary" href="{REPO}">View source ↗</a></div><p class="small">Typed choices. Explicit context. Independent verification.</p></div><div class="editor"><div class="editor-head">task.py <span>YOU DEFINE THE CONTRACT</span></div><pre><i>from</i> apixly_jev_harness <i>import</i> Task, Parameter

workflow = <b>Task</b>(observe=observe, verify=verify)

@workflow.<b>tool</b>("Inspect the selected job",
    parameters={{
        "job": <b>Parameter</b>(
            "Current failed job for this user",
            choices=current_jobs,
        )
    }})
def inspect(job):
    return service.inspect(job)</pre><div class="editor-foot">Goal → Tool choice → Parameter binding → Verified outcome</div></div></section><section class="loop"><div><small>01 / OBSERVE</small><strong>Explicit context</strong><p>Goal, facts, dialogue and current state.</p></div><div><small>02 / DECIDE</small><strong>Jev chooses</strong><p>Registered tools and meaningful parameter options.</p></div><div><small>03 / EXECUTE</small><strong>Program binds</strong><p>Resolve candidate IDs, check freshness and policy.</p></div><div><small>04 / VERIFY</small><strong>Prove completion</strong><p>Record actual results. Continue, review or exit.</p></div></section><section class="section"><div class="eyebrow">One reusable mechanism</div><h2>{"定义业务逻辑，复用运行时。" if zh else "Define your work. Reuse the runtime."}</h2><div class="cards"><article class="card"><div class="chip">TOOLS + PARAMETERS</div><h3>Meaning before values</h3><p>Describe each parameter, supply observed candidates, and bind dependencies in order. Jev selects references; it never invents arguments.</p></article><article class="card"><div class="chip">CONTEXT + HISTORY</div><h3>A useful working state</h3><p>Keep constraints, admitted messages and recent results. Older actions retain evidence references. Raw journals stay private.</p></article><article class="card"><div class="chip">AGENT INTERFACE</div><h3>Easy to discover and run</h3><p>Machine-readable spec, a runnable scaffold, offline syntax checks, typed Python and a task-oriented agent skill.</p></article></div></section><section class="section"><div class="proof"><div><div class="chip">EVIDENCE, WITH LIMITS</div><h3>Live browser path verified</h3><p>v0.1.0 evidence: real Jev + headless Camofox. Four tool executions. Local synthetic fixture.</p><p>Early review outcomes retained. Native desktop acceptance is pending: host last observed locked.</p></div><a href="{p}evidence.html">Inspect the evidence →</a></div></section><section class="section"><h2>{"从一份接口说明开始。" if zh else "Start with one contract."}</h2><div class="editor"><pre>jev-harness <b>spec</b>
jev-harness <b>init-task</b> task.py
jev-harness <b>check-task</b> task.py
jev-harness <b>run</b> task.py --goal "Reach target" --inputs '{{"target":3}}'</pre></div><p class="small">Python 3.10+ · Git-based installation · Inference is billable · Trusted scripts, not a sandbox</p><div class="actions"><a class="button secondary" href="{p}agent-contract.html">Installation &amp; task protocol</a><a class="button secondary" href="{p}spec.json">Machine-readable spec ↗</a></div></section></main>'''
    if zh:
        translations = {
            "One reusable mechanism": "一套可复用机制",
            "TOOLS + PARAMETERS": "工具与参数",
            "CONTEXT + HISTORY": "上下文与历史",
            "AGENT INTERFACE": "AI 接口",
            "Meaning before values": "先描述语义，再绑定值",
            "A useful working state": "保留有用的工作状态",
            "Easy to discover and run": "易发现、易编写、易运行",
            "Describe each parameter, supply observed candidates, and bind dependencies in order. Jev selects references; it never invents arguments.": "描述参数含义，提供现场候选，按依赖顺序绑定。Jev 选择引用，不凭空生成参数。",
            "Keep constraints, admitted messages and recent results. Older actions retain evidence references. Raw journals stay private.": "保留约束、准入对话和近期结果，较早动作保留证据引用。原始记录留在私有日志。",
            "Machine-readable spec, a runnable scaffold, offline syntax checks, typed Python and a task-oriented agent skill.": "机器可读 spec、可运行模板、离线语法检查、Python 接口和任务型 agent skill。",
            "Typed choices. Explicit context. Independent verification.": "类型化选择，明确上下文，独立结果验证。",
            "Explicit context": "明确上下文",
            "Jev chooses": "Jev 选择",
            "Program binds": "程序绑定",
            "Prove completion": "验证完成",
            "Goal, facts, dialogue and current state.": "目标、事实、对话与当前现场。",
            "Registered tools and meaningful parameter options.": "注册工具与有语义的参数候选。",
            "Resolve candidate IDs, check freshness and policy.": "解析候选 ID，检查现场与执行策略。",
            "Record actual results. Continue, review or exit.": "记录实际结果，继续、复核或退出。",
            "EVIDENCE, WITH LIMITS": "证据与适用范围",
            "Live browser path verified": "真实浏览器路径已验证",
            "v0.1.0 evidence: real Jev + headless Camofox. Four tool executions. Local synthetic fixture.": "v0.1.0 验收：真实 Jev + headless Camofox，四次工具执行，本地合成夹具。",
            "Early review outcomes retained. Native desktop acceptance is pending: host last observed locked.": "保留早期复核结果。原生桌面仍待验收；主机最近观察为锁屏。",
            "Inspect the evidence →": "查看验收证据 →",
            "Installation &amp; task protocol": "安装与任务协议",
            "Machine-readable spec ↗": "机器可读规范 ↗",
            "View source ↗": "查看源码 ↗",
            "Python 3.10+ · Git-based installation · Inference is billable · Trusted scripts, not a sandbox": "Python 3.10+ · Git 安装 · 推理付费 · 执行可信脚本，不是沙箱",
        }
        for old, new in translations.items():
            body = body.replace(old, new)
    return shell(
        "AI 易用的 Jev 原生任务运行时" if zh else "Jev-native agent loops for AI-authored tasks",
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
