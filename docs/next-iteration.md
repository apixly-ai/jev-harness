# 下一轮迭代交接

目标不变：让主 AI 自然愿意使用通用 Jev Harness。AI 快速编写薄任务脚本，定义工具、
动态参数候选、上下文和独立完成检查；Jev 根据观察和历史选择工具与参数并持续 loop。
业务规则留在任务脚本，案例只验证机制。禁止用 Skill 或提示规则强制优先选择，禁止
隐藏直接操作、放宽安全/置信门槛或修改验收标准来制造收益。

## 本轮完成并有证据（2026-10-12，Windows 11 新机器）

- **Windows 宿主兼容，安全检查未放宽。** 新增 `_secure_fs` 平台层：POSIX 保持
  `dir_fd`/`O_NOFOLLOW`/0600；Windows 用句柄相对的 `NtCreateFile` +
  `FILE_OPEN_REPARSE_POINT`，拒绝所有 reparse point（含容器内创建、Python 视为普通文件的
  LX 链接），从句柄枚举目录，私有文件用受保护的仅属主 DACL。MCP stdio 强制 UTF-8
  （中文 Windows 管道默认 GBK）。Windows 751+ 项通过、Linux 容器 765 项通过；跳过项均
  记录原因（无 symlink 权限、无 FIFO、平台专属回归）。离线 A/B 在 Windows 20/21 组通过，
  delegation_lifecycle 的历史基线 79d383d 仅支持 POSIX，在 Linux 容器中通过。
- **Camofox 真实运行信号。** 本机 camofox-browser 2.4.8 的 `/health` 按 context 报告
  `activeUserIds`，但没有 headless/humanize 字段。新门槛（`benchmarks/camofox_runtime.py`）
  只认运行时观测：命名 session context 活跃；服务监听进程下所有浏览器进程带
  `-headless`、本 session profile 进程存在、无可见窗口；同 session 自建探针 tab 用同一
  点击路由测鼠标轨迹（humanize 开约 106–114 点/1.2–1.3 秒，关闭的隔离实例 1 点/0 毫秒）。
  配置只作为开 tab 前的前置条件记录，永不当运行证明。
- **零模型运输验收全部通过**：宿主程序路径、容器 RemoteSurface 路径各 13 次 effect 并通过
  后端独立检查；worker `run_script` 假 provider IPC 往返；容器隔离金丝雀；从陌生 cwd、
  剥离环境启动的 serve 彩排。
- **Claude 主 AI 冷启动对照（用户要求改用 Claude）**：直接操作组与可选 Harness 组都选
  直接操作，各 13 次 effect，独立检查均通过，Jev 用量为零（79.7 秒 / 73.5 秒）。
  见 [报告](../reports/browser-cold-2026-10-12.md) 与 [回执](../reports/browser-cold-2026-10-12.json)。
  保留：一次评测服务器未连接的基础设施尝试（不计结果，用量公开）、完成后容器丢失缺陷。
- **通用接口改进**：quickstart 写明 `authorize(ctx, action)` 收到的
  `action.params == {'tool', 'arguments'}` 以及 `SurfaceTask` 用法（本轮金丝雀作者曾读错
  该结构并被安全地拦在 `needs_confirmation`）。

## 本机环境事实（新机器复现时核对，不要照搬）

- 主 AI：`benchmarks/primary_claude.py`，headless `claude -p`，`--tools ""`、
  `--setting-sources ""`、`--disable-slash-commands`、`--strict-mcp-config`、只批准评测
  服务器工具；init 事件记录实际工具清单，回执记录实际模型、回退与用量。子进程剥离
  `CLAUDE*`/`ANTHROPIC_*`/`MCP_*`/`TYPESAFE_*`/`JEV_*`，设 `MCP_TIMEOUT=120000`。
  Codex 适配器仍在（`primary_cli.py`），但本机 ChatGPT 账号不支持 `gpt-6.1-sol`。
- Windows AF_UNIX 在本轮出现系统级故障，Docker Desktop 后端无法启动；未重启电脑，
  改用 WSL Ubuntu 内的 dockerd（`--docker-wsl-distro Ubuntu`，路径映射到 `/mnt/<drive>`，
  运行期间保持一个附着的 `wsl.exe` 会话防止发行版空闲关停）。所有容器子进程不继承 stdin
  （`wsl.exe` 与 `docker exec -i` 会吞掉 MCP 请求流）。
- Camofox：独立 profile 目录、headless、humanize、命名 session `general`；Claude 结束会话
  时会直接终止 MCP 进程，serve 先写证据再关 tab/停容器，运行器只关 `owned-tab.json`
  记录的 tab、只停 `actor.json` 记录的容器。

## 下一步优先事项

1. **找出 Harness 路线真正有优势的任务形态，而不是继续加提示。** 本轮 13 控件固定表单
   上，主 AI 理由是“小表单、每步有反馈、写脚本无收益”。下一组同目标对照应换成路线未知、
   步骤更多或需要重复执行的浏览器/工作区任务（例如需要翻页发现目标、多个依赖参数、
   同一配置要对多个对象重复），并完整计算编写、修正、执行、核验成本。
2. **降低冷启动编写成本**：把一个可直接改的浏览器 TaskScript 模板（`SurfaceTask` +
   `RemoteSurface` + 范围授权 + 独立 verify）放进 `init-task --toolkit`，让 AI 用一次
   写入就能交给 Jev；仍然不能在提示里要求使用它。
3. 若要宣称 Claude 与此前 Codex 行可比，需要同一模型族重复对照；当前两者不可比。
4. 发布前照常运行 lint、覆盖率、打包、21 组离线 A/B、公开内容与站点检查；Linux 结果用
   容器复核。保留失败、未知用量与整段时间，不重复付费掩盖失败。

当前 recurring automation 保持 paused；此交接不授权静默恢复，也不更新个人 memory。
