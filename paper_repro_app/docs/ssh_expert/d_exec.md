# 执行链路设计规范：解析 → 检测 → 连接 → 流水线执行

依据代码核对：包位于 paper_repro_app/paper_repro_app/（app.py 同级子包）。提交路径已确认：create_task 落 queued → start_pipeline_execution 携内存 password/hosts → RemoteRunner.execute 开头 probe 选机，全败即 failed；probe 只测 TCP 3s、凭据不参与、config/别名不参与，是"自动连接检测失败"误报主源。

## 决策

**1. 端到端时序与状态机扩展**

```
主线程(提交)          后台线程 worker                DB 落库
resolve_ssh_profile
parse_ssh_candidates
create_task            →                         status=queued, step=connect
start_pipeline_execution ──→ ①status=connecting
                           ②L0 本地检查(host/user/端口合法、key 存在/PEM 可写、
                              password|key|agent|config 至少一源)
                           ③L1 DNS+TCP 探测每候选≤4s    ── log 逐台写明细
                           ④L2 paramiko 真实握手≤12s   ── log 写结果分类
                              ├成功：选定机 host/user/port 写回任务行
                              │     status=running, step=prepare → 现有 10 步
                              └全败：status=failed, step=connect
                                    log 存 phase=connect 分段明细 JSON
```

状态机结论：DB 新增连接中态 status="connecting"、阶段标记 current_step="connect"（不并入 10 步流水线；步进器对未知 step 已回落索引 0，无回归）。价值：监控 UI 三态可辨（排队/连接中/执行中），历史列表可看出"从未进入执行即失败"的任务；失败不再与流水线步骤失败混淆。

**2. 检测位置：execute() 开头的前置阶段，而非流水线远端步骤**

预检放后台线程内、execute() 开头、流水线循环之前，作为进程内函数 connect_candidates()。理由：远端每一步都要先有 SSH 会话，"检测=建会话"，物理上不可能作为远端第 0 步（无会话即无 shell）；放 execute 开头可复用现有 connect_kwargs 构造、重试与 cancel 检查（单一实现守卫），test_ssh_connection 与 L2 共用同一握手路径。L1 只分类记录不否决——TCP 不通（慢/丢包/防火墙限速）不等于不可用，L2 结果为准，消除现 3 秒 probe 误报。预检失败任务照常 failed 落库，监控失败分支渲染"连接检测明细"面板，按候选逐行分段展示原因与对应动作，废弃"全部不可达"单句模板。

**3. 多候选轮转终版**

- 顺序=候选解析序（目标串优先）。L1 不可达（拒绝/超时/DNS）→ 换下一台。
- L2 认证失败：默认转移（同密码同 key 场景下常见"某台实例被回收/端口失效"，转移有真实收益），但配"同因短路"：user+key+password 完全相同时，一旦出现首台 Authentication failed 即判定为凭据级错误，立即终止不再逐台空转。风险说明：若凭据全错，转移只是把失败延后；短路后代价收敛到 1 台握手（≤16s），且明细会写明"凭据级错误"引导注入公钥/改密码，避免 n×16s 放大与根因模糊。
- 预算：单台 L1≤4s+L2≤12s，总预算 min(60s, 台数×16s)，超时按 failed(connect, timeout) 落库。
- 失败消息模板（无 emoji）：
```
[连接检测失败] 已按序尝试 N 台候选，均未能建立 SSH 会话。
分段明细：1) user@host:port - 不可达(TCP 超时 4s)；2) user@host:port - SSH 认证被拒绝(Authentication failed)
请按类别操作：地址类→确认实例已开机并粘贴控制台最新登录命令；凭据类→注入公钥或核对密码；端口类→确认 4xxxx 实际端口。
```

**4. 取消 / 超时 / 重试 / 历史重跑**

cancel_event 每台探测前后检查，L2 握手受 12s 上限约束不可即时中断，与现有 0.2s 轮询语义一致；连接失败不整轮自动重试（防双倍延迟与远端副作用），"重新执行流水线"即用户侧重试；现有 max_retries 保留给会话中途断线。历史重跑回落：task_hosts/task_passwords 仅内存，进程重启即失 → 无内存时回落单机候选（host/user/port/ssh_key_path 均在库），password 为空自动走 key/agent，UI 明示"历史任务未保留密码与多机清单，将按记录主机与现有私钥重试"。多候选刻意不落库：AutoDL 地址每次开机变化，旧清单反成误导源；引导到提交页粘贴新连接串。

**5. 日志与遥测**

检测明细双写：StepLogger（app.log，trace 关联，供系统排查）+ on_step（任务 log 滚动窗口与结果 JSON 可见，供用户）。脱敏规则：密码零落库零落日志（消息模板内引用时用 ***）；私钥只记文件名 basename 与公钥指纹，诊断只显示公钥前 40 字符（沿用现逻辑）；主机/user/port 为正常遥测保留。统一在单一出口清洗：logging Filter（app.log 侧）+ TaskStore 写前 sanitize()（DB 侧）双保险，正则覆盖 password/passwd/pwd= 值、-----BEGIN...PRIVATE KEY----- 全文块。

## 可执行变更

1. remote_runner.py：新增 connect_candidates(task, cancel_event) → 返回 (chosen|None, 诊断明细 dict)；内部 L0（复用 detect_ssh_auth_sources）/L1（probe_host 升级：getaddrinfo+TCP，分类 dns/refused/timeout，4s）/L2（paramiko 握手一次，10s）+ 轮转 + 同因短路 + 总预算；execute() 开头用其替换现有 probe 直判段，诊断明细并入失败 result。
2. ssh_utils.py：抽出 build_connect_kwargs(host,user,port,key,password) 供 test_ssh_connection、L2、execute 共用，保证手动"测试 SSH 连接"与自动预检判定一致。
3. storage_utils.py：_run_pipeline_in_background 线程入口先 update_task_status(task_id,"connecting",...,"connect")；成功选机后写回 host/user/port；失败分支透传 phase=connect 明细 JSON。
4. database.py：新增 TaskStore.update_connect_info(task_id, host, user, port)（仅 UPDATE，schema 不变，DB version 保持 8）。
5. app.py：label_map/get_status_color/status_labels 三处补 connecting（色板复用 running 青色，文案"连接检测中"）；_auto_refresh_monitor 与 live_monitor 的活跃条件并入 connecting；失败分支新增"连接检测明细"分段面板（读 log 中 phase=connect）。历史 tab 状态字典同步补 connecting。
6. task_utils.py：get_status_color 补 connecting；get_step_order 不动（connect 索引回落已兼容）。
7. 提交页：cloud_host 默认占位 my-server.example.com 空输入时不作为候选入列（消除虚假第二候选）；测试 SSH 连接按钮提示与自动预检同判。
8. logger_utils.py/logging_config.py：新增 redact_sensitive()，logging Filter 与 TaskStore 写前统一调用。
9. 测试：新增 4 条用例（L1/L2 分类、认证同因短路、历史重跑回落单机、脱敏断言），只增不改既有断言，保持 pytest 全绿。
