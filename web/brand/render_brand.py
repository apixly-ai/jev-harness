"""Rebuild the original bilingual Jev Harness vector artwork."""

from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
FONT = "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Arial, PingFang SC, sans-serif"
MONO = "SFMono-Regular, Consolas, Liberation Mono, monospace"


def glyph(x=0, y=0, scale=1):
    return f"""<g transform="translate({x} {y}) scale({scale})" fill="none" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
      <path d="M10 29V10h28" stroke="#c6f67a"/><path d="m31 3 8 7-8 7" stroke="#c6f67a"/>
      <path d="M53 10h19v28" stroke="#7de3e5"/><path d="m79 31-7 8-7-8" stroke="#7de3e5"/>
      <path d="M72 53v19H44" stroke="#c6f67a"/><path d="m51 79-8-7 8-7" stroke="#c6f67a"/>
      <path d="M29 72H10V44" stroke="#7de3e5"/><path d="m3 51 7-8 7 8" stroke="#7de3e5"/>
      <circle cx="41" cy="41" r="3" fill="#eef0eb" stroke="none"/>
    </g>"""


def begin(width, height, title, desc, rounding=28):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
    <title id="title">{escape(title)}</title><desc id="desc">{escape(desc)}</desc>
    <defs>
      <radialGradient id="glow"><stop stop-color="#c6f67a" stop-opacity=".075"/><stop offset="1" stop-color="#080b0f" stop-opacity="0"/></radialGradient>
      <linearGradient id="edge"><stop stop-color="#c6f67a"/><stop offset="1" stop-color="#7de3e5"/></linearGradient>
      <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="m1 1 5 3-5 3" fill="none" stroke="#64715f" stroke-width="1.6"/></marker>
    </defs>
    <style>text{{font-family:{FONT}}}.mono{{font-family:{MONO}}}</style>
    <rect width="{width}" height="{height}" rx="{rounding}" fill="#080b0f"/>
    <ellipse cx="{width * 0.78}" cy="{height * 0.25}" rx="{width * 0.35}" ry="{height * 0.7}" fill="url(#glow)"/>
    <path d="M32 .5H{width - 32}" stroke="#2b3426"/>
    '''


def text(x, y, value, size=20, fill="#a3aaa5", weight=400, cls="", more=""):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" class="{cls}" {more}>{escape(value)}</text>'


def hero(zh=False):
    title = (
        "Jev Harness · 工具你来定义。下一步交给 Jev。"
        if zh
        else "Jev Harness · Your tools. Jev’s next move."
    )
    desc = (
        "观察、选择、执行、验证。Python 原生，程序提供类型化候选，独立校验结果。"
        if zh
        else "Observe, choose, execute, verify. Python-native loops with program-supplied typed choices and independent verification."
    )
    s = begin(1440, 850, title, desc)
    s += glyph(66, 61, 0.72)
    s += text(145, 105, "jev-harness", 34, "#eef0eb", 650)
    s += text(
        69,
        182,
        "JEV-NATIVE AGENT LOOPS" if not zh else "JEV 原生智能体循环",
        14,
        "#c6f67a",
        650,
        "mono",
        'letter-spacing="2"',
    )
    headlines = (
        ["工具你来定义。", "下一步交给 Jev。"] if zh else ["Your tools.", "Jev’s next move."]
    )
    s += text(65, 285, headlines[0], 78 if zh else 83, "#eef0eb", 750, more='letter-spacing="-3"')
    s += text(65, 390, headlines[1], 74 if zh else 76, "#c6f67a", 750, more='letter-spacing="-3"')
    lines = (
        ["让 Jev 在你提供的候选里选择。", "程序执行，用新观察验证结果。"]
        if zh
        else [
            "Let Jev choose from the choices you supply.",
            "Your program acts. A fresh check proves the result.",
        ]
    )
    for i, line in enumerate(lines):
        s += text(69, 458 + i * 37, line, 23 if zh else 21, "#a3aaa5")
    s += '<rect x="69" y="548" width="237" height="47" rx="23.5" fill="#151c11" stroke="#34442b"/>'
    s += text(93, 579, "定义 → 运行 → 验证" if zh else "Define → run → verify", 16, "#c6f67a", 600)
    s += text(
        325,
        579,
        "观察保留，结果可追溯" if zh else "Keep the trace. Know the outcome.",
        16,
        "#8b948c",
    )

    # A compact loop illustration shows the boundary between model choice and code.
    s += '<rect x="866" y="145" width="505" height="481" rx="22" fill="#0f1419" stroke="#273039"/>'
    s += text(
        893,
        184,
        "ONE BOUNDED LOOP" if not zh else "一次有边界的循环",
        12,
        "#a0aa9f",
        600,
        "mono",
        'letter-spacing="1.5"',
    )
    s += '<path d="M1319 541h23V238h-23" stroke="#34412e" stroke-width="2" fill="none" marker-end="url(#arrow)"/>'
    entries = [
        (
            "01",
            "观察" if zh else "Observe",
            "程序读取当前状态" if zh else "Your program reads the state",
            "#7de3e5",
        ),
        (
            "02",
            "选择" if zh else "Choose",
            "Jev 选择候选工具与参数" if zh else "Jev picks a tool and typed choices",
            "#c6f67a",
        ),
        (
            "03",
            "执行" if zh else "Execute",
            "程序核对并调用工具" if zh else "Your program checks and calls",
            "#7de3e5",
        ),
        (
            "04",
            "验证" if zh else "Verify",
            "用新观察确认目标结果" if zh else "A fresh observation checks the goal",
            "#c6f67a",
        ),
    ]
    for i, (number, label, detail, color) in enumerate(entries):
        y = 207 + 92 * i
        s += f'<rect x="891" y="{y}" width="425" height="75" rx="12" fill="{"#162012" if i == 1 else "#141b21"}" stroke="{"#486434" if i == 1 else "#273039"}"/>'
        s += text(910, y + 30, number, 14, color, 600, "mono")
        s += text(951, y + 30, label, 22, "#eef0eb", 600)
        s += text(951, y + 55, detail, 14, "#99a49b")
        if i < 3:
            s += f'<path d="M1103 {y + 78}v11" stroke="#53604e" stroke-width="2" marker-end="url(#arrow)"/>'
    s += '<circle cx="905" cy="598" r="4" fill="#c6f67a"/>'
    s += text(
        918,
        603,
        "完成 = 独立校验通过" if zh else "Done = independently verified",
        13,
        "#a8b29d",
        500,
        "mono",
    )

    s += '<path d="M69 690H1371" stroke="#273039"/>'
    labels = [
        ("Python", "与你的工具一起运行" if zh else "Fits your own tools"),
        (
            "类型化候选" if zh else "Typed choices",
            "候选由程序提供" if zh else "Supplied by your program",
        ),
        (
            "独立验证" if zh else "Independent checks",
            "结果明确，未知保留" if zh else "Outcomes and unknowns stay visible",
        ),
    ]
    for x, (label, detail) in zip([69, 523, 974], labels):
        s += text(x, 745, label, 26, "#eef0eb", 600)
        s += text(x, 780, detail, 17, "#8c968d")
    s += '<path d="M467 725v55M918 725v55" stroke="#273039"/>'
    return s + "</svg>\n"


def workflow(zh=False):
    title = "从目标到可验证结果" if zh else "From a goal to a verified outcome"
    desc = (
        "主模型规划，程序观察并提供候选，Jev 选择，程序执行并独立验证。"
        if zh
        else "The primary agent plans. The program observes and supplies choices. Jev chooses, then the program executes and independently verifies."
    )
    s = begin(1440, 630, title, desc)
    s += glyph(63, 43, 0.55)
    s += text(127, 82, "jev-harness", 25, "#eef0eb", 600)
    s += text(64, 151, title, 46 if zh else 45, "#eef0eb", 650, more='letter-spacing="-1.5"')
    s += text(
        64,
        197,
        "规划留给主模型，选择交给 Jev，执行与证明由程序负责。"
        if zh
        else "The agent plans. Jev chooses. Your program executes and proves the result.",
        22,
        "#a3aaa5",
    )
    data = [
        (
            "观察" if zh else "Observe",
            "当前状态" if zh else "Current state",
            "工具与参数候选" if zh else "Tool and parameter choices",
            "PROGRAM",
            "#7de3e5",
        ),
        (
            "选择" if zh else "Choose",
            "已有工具与类型化选项" if zh else "Registered tools, typed options",
            "选择下一步" if zh else "Select the next move",
            "JEV",
            "#c6f67a",
        ),
        (
            "执行" if zh else "Execute",
            "检查边界与新鲜度" if zh else "Check bounds and freshness",
            "调用已注册工具" if zh else "Call the registered tool",
            "PROGRAM",
            "#7de3e5",
        ),
        (
            "验证" if zh else "Verify",
            "获取新的观察" if zh else "Get a new observation",
            "独立核对目标结果" if zh else "Check the outcome independently",
            "PROGRAM",
            "#c6f67a",
        ),
    ]
    for i, (label, a, b, actor, color) in enumerate(data):
        x = 64 + 337 * i
        s += f'<rect x="{x}" y="255" width="301" height="204" rx="16" fill="{"#152010" if i == 1 else "#10171d"}" stroke="{"#486434" if i == 1 else "#2a333b"}"/>'
        s += text(x + 22, 290, f"0{i + 1}  {actor}", 12, color, 650, "mono", 'letter-spacing="1"')
        s += text(x + 22, 343, label, 30, "#eef0eb", 650)
        s += text(x + 22, 388, a, 17, "#a3aaa5")
        s += text(x + 22, 418, b, 17, "#a3aaa5")
        if i < 3:
            s += f'<path d="M{x + 309} 357h20" stroke="#637259" stroke-width="2" marker-end="url(#arrow)"/>'
    s += '<path d="M1228 478v44H214v-44" stroke="#34422c" stroke-width="2" fill="none" marker-end="url(#arrow)"/>'
    s += '<rect x="549" y="502" width="344" height="38" rx="19" fill="#080b0f" stroke="#2b3725"/>'
    s += text(
        571,
        527,
        "未完成？用新观察继续循环" if zh else "Not done? Continue with a fresh observation",
        14,
        "#c6f67a",
        500,
    )
    s += text(
        64,
        588,
        "程序给出候选；模型不会生成可执行代码。"
        if zh
        else "The program supplies choices; model output never becomes executable code.",
        18,
        "#8c968d",
    )
    return s + "</svg>\n"


def social(zh=False):
    title = (
        "Jev Harness · 工具你来定义。下一步交给 Jev。"
        if zh
        else "Jev Harness · Your tools. Jev’s next move."
    )
    s = begin(1200, 630, title, title, rounding=0)
    s += glyph(66, 57, 0.66)
    s += text(141, 99, "jev-harness", 34, "#eef0eb", 650)
    lines = ["工具你来定义。", "下一步交给 Jev。"] if zh else ["Your tools.", "Jev’s next move."]
    s += text(62, 234, lines[0], 79 if zh else 90, "#eef0eb", 750, more='letter-spacing="-3"')
    s += text(62, 345, lines[1], 79 if zh else 90, "#c6f67a", 750, more='letter-spacing="-3"')
    s += text(
        65,
        415,
        "Python 原生循环 · 类型化候选 · 独立验证"
        if zh
        else "Python-native loops. Typed choices. Independent verification.",
        25,
        "#a3aaa5",
    )
    s += '<path d="M65 478H1135" stroke="#2a3429"/>'
    for i, label in enumerate(
        ["观察", "选择", "执行", "验证"] if zh else ["Observe", "Choose", "Execute", "Verify"]
    ):
        x = 65 + i * 277
        s += text(x, 539, f"0{i + 1}", 18, "#7de3e5" if i % 2 == 0 else "#c6f67a", 600, "mono")
        s += text(x + 40, 539, label, 23, "#eef0eb", 550)
        if i < 3:
            s += f'<path d="M{x + 202} 531h30" stroke="#65745b" stroke-width="2" marker-end="url(#arrow)"/>'
    return s + "</svg>\n"


if __name__ == "__main__":
    for name, render in (("hero", hero), ("workflow", workflow), ("social", social)):
        for zh in (False, True):
            suffix = ".zh-CN" if zh else ""
            (ROOT / f"{name}{suffix}.svg").write_text(render(zh), encoding="utf-8")
