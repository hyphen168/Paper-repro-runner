# 专家组报告 · 命令候选与确认流（c_cmd）

## 决策

**总原则：不确定性一律落到"用户看得懂的选一/选二/选三"，绝不出现技术白屏。auto 模式从"提交瞬间静默取 best_candidate"改为"提交前先分流、让用户做最终裁决"。**

1. 提交流程插入点。位置：提交任务 tab 内「卡片 2 运行方式」容器之后、提交主按钮之前，新增「智能识别结果」区；仅 auto/run 模式可见（safe 不动，run 的手填命令本来就是兜底）。识别由提交点击或显式「识别候选」按钮惰性触发（不进 rerun 重算、不默认爬网），保证 AppTest 确定性。提交时三分支：
   - A 唯一高置信（crawler 第一名 score 达到次名 2 倍且证据与 README 一致；user_input 恒最高）：跳过确认直接跑，只 toast 加一行说明并写档案。例外：档案中同 repo 有"上次成功配置"时优先预选该项并提示"沿用上次成功配置"，满足换参数/换机秒配（案例⑦）。
   - B 多候选（仓库候选并列、或同一仓库多个入口/参数风格不可假设）：拦截本次提交，渲染确认面板——候选命令 radio（多于 3 个转 selectbox）+ 详情卡片 + 「数据集自动项」勾选（默认开，对应高级选项自动发现+自动下载，档案命中时预填 data_config 并展示），一次点击「用所选配置提交」才建任务，杜绝误跑（案例①②④）。
   - C 无识别：不再直接报错，改为引导流——自动建议并预切到 run 模式预填 run_command 输入框，顶部给"仓库辅助提示"面板（探测到的 *.py 列表 + README 训练段摘录），下方二选一：「粘贴 README 里的训练命令」或「换仓库候选重试」。入口已确认可跑但风格存疑（案例① trainer.py + --arch）也走此态，由用户补参数值，系统不猜超参。

2. 候选卡片 UI 与置信度。卡片三要素缺一不可：命令（code 风格，含 ${PAPER_REPRO_DATA_CONFIG} 占位）、依据（README 行号摘录或探测到文件路径，不写无出处猜测）、置信徽标（复用 status-dot+meta-pill：绿=高置信·档案验证、黄=中置信·README 提及、灰=低置信·需人工确认）。证据来源只认三类：档案命中 > README 摘录 > 实际探测文件。HTML 骨架与文案见可执行变更 2。

3. 换论文 3 步引导与失败模板。提交页论文链接旁常驻一行可展开引导「换了新论文？3 步跑通」：第 1 步 粘贴新论文 arXiv 链接（候选框留空则自动重识别）；第 2 步 点击「识别候选仓库」，对照候选卡（星标/更新时间/简介）或直接粘贴仓库地址；第 3 步 系统记忆论文-仓库绑定并进入入口确认。识别失败给固定模板（见变更 6），含 GitHub 搜索建议链接模板，并针对两类常见误判给专属文案：模型 zoo 仓库（案例② hubconf.py 无训练脚本）与 monorepo 深层入口（案例③ mnist/main.py），避免用户误以为程序故障。

4. 失败后调整命令重跑。监控页失败分支保留现有 LogAnalyzer 诊断，其下新增「调整命令后重跑」expander：run_command 与 data_config 均为可编辑预填框（优先取该任务 DB 值，其次取档案中同 repo 最近成功值）；确认=新建任务（复制原任务字段、auto_run 置 0、run_command 替换）后走既有 P0-2 密码流——内存密码可用则直接 start_pipeline_execution，失效则复用 rerun_need_pwd 现场补输模式。密码始终只在进程内存，不落库不落档案（明文约束保持）。

5. 与仓库档案（a 组）联动。新增单一档案 ~/.paper_repro_app/repo_profiles.json（LocalConfigStore.config_dir 内），a 组 CRUD 与本流同源同文件：确认过的候选、成功任务回写、云端 ModelDiscovery 回报的 entrypoint/reason 全部 upsert；提交预检与失败重跑先读档案。由此实现"论文→仓库→命令"三层记忆，完成同仓库二次运行秒配（案例⑦）。档案 schema 不含密码字段。

## 可执行变更

1. app.py 提交区。
   - 渲染点：`run_mode` radio 卡片之后、`submitted` 按钮之前插入 `_render_detect_zone(...)`；`crawler.evaluate_and_rank_candidates(...)` 之后将丢弃的 `candidate_list` 传入新门卫函数 `_gate_auto_confirm(crawl_result, archive_profiles, run_mode)`，返回 ("direct"|"confirm"|"guide", payload)，direct 沿用现有 create_task 段（仅补档案写入），confirm/guide 以 st.stop() 拦下本轮提交并渲染面板。
   - 新模块级函数便于单测：`_build_command_candidates`（合并档案命中 + 仓库 tree/README 探测结果）、`_render_confirm_panel`（radio/selectbox + 详情卡 + 数据集 checkbox + 「用所选配置提交」；confirm 时直接消费候选携带的 repo_url/clone_url，不二次爬取）、`_render_none_guidance`。
   - session keys 固定为 `cmd_detect_cands / cmd_detect_choice / cmd_dataset_auto / cmd_pending_payload`，任务创建成功后清空防串扰；仓库探测全部 try/except，失败降级为"引导粘贴 README 训练段"，绝不抛异常。默认 safe 模式路径零改动，AppTest 0 异常与 pytest 88 基线不回归。

2. ui_theme.py 候选卡片（HTML 骨架，无 emoji，供 a 组复用）：
   ```html
   <div class='panel' style='padding:.6rem .8rem;margin:.35rem 0;'>
     <div style='display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;'>
       <span class='status-dot' style='background:#00ffa3;'></span>
       <code style='flex:1;'>python trainer.py --arch resnet20 --data "${PAPER_REPRO_DATA_CONFIG}"</code>
       <span class='meta-pill'>高置信 · 档案验证</span>
     </div>
     <div style='color:var(--text-secondary);font-size:.8rem;margin-top:.3rem;'>
       依据：README Quick Start L12-15 训练命令 + 探测到顶层 trainer.py（--arch 参数风格）
     </div>
   </div>
   ```
   - 文案规格：命令标题行 + 依据行 + 徽标；选中项描边用 cyan（radio 同步高亮）。新增 `build_candidate_card_html(cand)` 纯字符串构建器；APP_CSS 仅补 3-4 条 `.cand-*` 布局规则，不引入新框架与 JS。

3. model_discovery.py 入口白名单扩展。由 [train.py, tools/train.py, scripts/train.py] 扩为 +trainer.py、main.py、app.py、detect.py、predict.py、run_train.py 及一层子目录（train/、mnist/ 等）内的同名脚本；同层多命中时不武断选一，把全部命中写入 payload.candidates 与 reason（含"找到的文件清单"），供 UI 确认面板与档案反哺；auto 直跑仍以 `--help` 含 `--data` 为必要条件，`--arch` 风格一律交用户裁决。

4. 失败重跑（`_render_monitor_content` 的 failed 分支）。在 SSH 认证排查 caption 之后加 expander：text_area 预填（task 的 run_command，空则取档案）、data_config 预填；「创建并重跑」= 复制字段 create_task（auto_run=0）后复用现有 `_get_exec_state().get("task_passwords")` 内存密码，无密码则置 `rerun_need_pwd_{new_id}` 走既有补输分支。不改 DB schema、不动 start_pipeline_execution 签名。

5. 新增 repo_archive.py（a 组档案落地于此）。位置 `LocalConfigStore.config_dir / repo_profiles.json`；schema：`{repo_url: {paper_url, entrypoint, run_command, data_config, host, tune_args, success_count, last_success_at, candidates:[{cmd, reason, confidence}], updated_at}}`；接口 `get_profile / get_by_paper / upsert_profile / note_success(task, model_payload)`；写入失败仅 warning 不阻断提交；无密码字段。

6. 文案模板（原样使用，中文无 emoji）。
   - 无仓库匹配：「未能从论文页确认官方代码仓库，下一步三选一：1 用这个搜索链接找实现仓库并粘贴到候选框 → https://github.com/search?q={论文标题关键词}&type=repositories ；2 回论文页找 Code / Official implementation 链接直接粘贴；3 重新粘贴 arXiv 地址再识别。选好后系统会继续帮你确认训练入口。」
   - 有仓库无入口 / 模型 zoo：「仓库 {repo} 可访问，但没找到可训练入口，常见原因：它只是模型定义/权重库（只有 hubconf.py，没有训练脚本）。建议二选一：1 在 README 的 Train/Usage 段复制训练命令粘贴到下方；2 换一个带训练脚本的实现仓库。以下为自动探测结果供你对照：{顶层 *.py 列表}；README 训练段摘录：{摘录 200 字内}。」
   - monorepo 深层入口：「入口在子目录里：{repo}/mnist/main.py。系统不会擅自假设子目录命令，请二选一：1 用自动生成的候选命令（cd mnist 后执行）直接跑；2 粘贴 README 中子目录的原始命令。」
   - 高置信直跑说明句：「已按唯一高置信候选直接启动：{repo} / {entrypoint}。如需换入口，可在下方改选候选或改用自定义命令。」
   - 秒配说明句：「该仓库有上次成功记录，已优先沿用其命令与数据集配置（可改选）。」
