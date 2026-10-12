# 下一轮迭代交接

目标：让主 AI 自然愿意使用通用 Jev Harness。AI 能快速编写薄任务脚本、定义工具与
动态参数候选、提供独立完成检查；Jev 根据观察和历史选择工具与参数并继续 loop。
业务规则放在任务脚本中，案例仅验证机制。禁止用 Skill 或提示规则强制优先选择，
禁止隐藏直接操作、放宽安全/置信门槛或造搜索迷宫来制造收益。

## 已完成并有证据

- 源码版本 0.3.0：Workspace/HTTP/Camofox 来源工具包、懒加载 TaskScript、统一 MCP
  两条执行路线、目标绑定描述、结构化结果、caller execution-name、原始报告分页。
- 新 `quickstart` 离线 API 卡约 2.6 KB；完整 `spec` 保留。EvidenceTask 工具阶段只给
  参数契约、数量及三个短提示，绑定阶段保留全部最新候选。观察去重、验证器完整
  provenance、novel quote eligibility 与 callback/Action identity 回归均已加入。
- 一次 prepared-script 自由选择：给普通“减少顺序客户端交互”目标，未指定路线、
  关闭产品 Skills，AI 自选 Jev。11 次效果/18 请求，Jev loop 8.287 秒，整轮 51.330 秒，
  三类原始来源与状态转换独立验收通过。默认 neutral 选择仍 direct，不能宣称普遍优先。
- 单独 current-repository 合成 Jev 功能验收：10 effects、16 requests、6.142 秒，三类
  source/version/hash/span 与 closed state-transition 检查通过；不含 AI 编脚本成本。
- 冷启动 repo 对照：network-none Docker 中普通 sh/Python 经 MCP；native control 与
  optional-harness 两组都选择 direct，没有编写/执行 harness task，事实证据均通过。
  native 初次 raw 格式因未明确 envelope/label enum 被拒，posthoc shape adapter 后
  factual score 通过；原始失败/文件/用量/耗时未改。未来 prompt 已明确 schema，未重复付费。
- 零模型 Docker canary 通过：空 work、只读 corpus/runtime、无 oracle/凭证/socket mount，
  冻结作者脚本后独立 worker 使用 IPC host provider；真实 TypeSafe key 留在宿主。
- 中英文网站与文档已同步；本地 headless Camofox 40 项网页交互、28 张截图通过。

证据：[自由选择及负面结果](../reports/adoption-2026-10-12.md)、
[冷启动对照及格式修正](../reports/cold-authoring-2026-10-12.md)。真实模型、实际/未知用量、
整段时间按各自作用范围记录；不把 cached-input 当额外 tokens，不推测价格或发票费用。

## 下一步优先事项：真实 browser 冷启动

已实现以下 benchmark-only 接线，可继续完成验收：

- `benchmarks/browser_cold.py`：普通 JS 合成通知配置后台、server-owned draft 状态、
  direct/optional MCP、共享受限 Browser Broker、冷 TaskScript 运行入口。
- `scripts/cold-bridge/browser_surface.py`：可导入 RemoteSurface。容器仅提交观察票据、
  opaque action ID 和命名填充值；宿主保留原始 Camofox targets，并复用原有解析/刷新检查。
- `tests/test_browser_cold.py`：11 个边界回归，含 IPC 响应目录 symlink 保护。

目标为：为当前活跃项目创建工作日故障摘要，包含 failed/blocked、排除 success/archived，
使用给定时区和现有 preview inbox，只保存 draft；独立检查真实 backend 保存字段、次数。
初始不提供导航路线、控件 ID 或 active-project 答案。预计 12–16 个 UI effects。

**当前阻塞是真实运行信号，不是代码编译：** 零模型 canary 在第一个 effect 前停止，
`general /health` 在 open tab 后仍报告 browserRunning/browserConnected=false、humanize=null。
源码只读排查发现全局 `browser` 与 FULL_PROFILE 的独立 `launchPersistentContext` 可能
不共用该健康字段。不能删除 gate 或从配置偏好推断运行时状态。失败证据留在私有
`local-results/browser-cold-transport-20261012/failure.json`；0 模型/0 effects/0 保存。
本轮 owned tabs 均已关闭，未重启服务或改浏览器身份。

1. 先读 AGENTS.md、当前 browser_cold/cold_authoring 与 Camofox 对应源代码，补实际
   full-profile engine 的 headless/humanize 证据和行为回归；区分配置与运行证据。
2. 复用 `general`、headless `CAMOFOX_INTERACTIVE=off`、humanize=true，只关闭自己创建的 tab。
   不重启 shared service，不探测锁屏 Mac、不绕锁屏或索要密码。
3. 零模型 browser 原语及 Docker worker 运输验收通过后，做同目标、同能力/权限/预算的
   direct-only 与 optional-harness 冷启动 pair。保留 shell 和直接自动化，不能为了胜出禁用。
4. 使用 `SurfaceTask(RemoteSurface(...), values=inputs['values'], verify=...check_goal(),
   allowed_origins=..., authorize=scoped_policy)`，业务验收由共同 host checker 对实际保存状态
   检查；不把业务 route 放进 core。记录 native-before/hybrid/委派效果，不混成 fully delegated。
5. 用户已允许本机配置的 TypeSafe 凭证做有界合成验收；宿主 bridge 保管，不进聊天/actor。
   沿用 24 effects、100 秒、50 请求上限；一次 primary turn，未知效果先对账、不自动付费重试。
   不访问客户或生产数据。Primary requested/resolved model、per-model 实际/未知 usage 和
   全轮 authoring/discovery/run/verification 时间分开记录。

CLI：`python benchmarks/browser_cold.py describe`；
`serve --directory NEW_PRIVATE_DIR --arm native|optional --wheel WHEEL --variant 0`
和可选 `--live --credential-file HOST_ONLY_PATH`。需要
`--headless-config EXPLICIT_PLIST`，它只提供配置证据，不能替代运行信号。
先查看 `--help` 与当前实现，不使用历史 tab ID。Root 主模型 benchmark 禁用了 builtin host
shell，实际操作是受限原生 browser API / Docker shell 经 MCP；不能冒充 Codex 内置 host shell。

## 发布与协作

按 repo 的 lint、coverage、package、offline A/B、public/site 检查发布。主页围绕优势和
通用机制，详细证据保留失败与 unknown；GEO 的抓取/索引/发现分开，不重复提交网址。
当前 recurring automation 保持 paused；此交接不授权静默恢复。后台 owner 通知仅具体成果、
阻塞/风险变化或真实决策点，不发空 heartbeat。不要更新个人 memory，除非用户另行明确要求。
