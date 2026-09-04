## 审计报告：SSH「自动连接检测失败」根因链与误导性检测缺陷

以下全部结论均直接引自代码，行号以当前工作区文件为准。

### 一、根因链（按影响排序）

根因主链：提交时 `host` 先经 `resolve_ssh_profile` 正确解析（app.py:858），随即被 `parse_ssh_candidates` 的二次解析产物覆盖（app.py:878-880），此后 `RemoteRunner.execute` 只凭 **TCP 连通性** 判定可用性（remote_runner.py:719），超时 3 秒、不校验凭据、不读 ssh_config、不做 SSH 握手；全部失败时回一条模板化「均无法连接」消息（remote_runner.py:731-741）。用户看到的是「不可达」，但真实断点在解析/探测，而非网络。

**R1（P0）候选串二次解析会制造一个「解析出来必然不可达」的主机——最可能的直接原因**
- remote_runner.py:90-94：`elif "@" in line` 分支把 `@` 之后整段当 host，不做空白截断。占位符宣传的格式（app.py:687 placeholder `root@123.45.67.89 -p 22`）会解析出 host=`"123.45.67.89 -p 22"`。probe 对含空格的假主机名做 DNS 解析必失败。
- app.py:878-880：`host_candidates[0]` 覆盖掉 app.py:858 里解析正确的结果，任务以垃圾 host 入库并进入探测。
- 对照：ssh_utils.parse_ssh_target 对同一串解析正确（ssh_utils.py:37-43 能收尾部 `-p`）→ 顶部 caption 显示「已自动识别」正常，用户据此确信信息正确，行为却走候选串 → 「明明对却不可达」。
- 现象：提交失败消息里的 `tried` 串出现 `root@connect…-p 38662:22` 这类畸形主机。
- 最小修复：`parse_ssh_candidates` 的 `@` 分支先按空白截断 host，再就地解析尾部 `-p N`；或删除两套解析器，统一调 `parse_ssh_target`（见冗余节）。

**R2（P0）probe 3 秒单次 TCP 超时系统性误杀可达主机**
- remote_runner.py:56-65（默认 `timeout=3.0`）、719、727。
- 执行链路真连接容忍 30/60/60 秒（remote_runner.py:773-775），探测却只给 3 秒；Windows DNS 慢解析、AutoDL 区域高延迟、运营商静默丢 SYN 包（Windows TCP 默认 21 秒才超时）、纯 IPv6 路由缺失时，3 秒一律误判 False。
- 现象：实例确实开着、`ssh` 命令 10 秒内能通，提交却报「无法连接」。
- 最小修复：探测超时提到 ≥8s 且每候选重试 2 次；失败分支区分 DNS/超时/拒连并给出不同文案。

**R3（P0）探测不读凭据、不读 ssh_config/别名，且早于凭据检查**
- remote_runner.py:719 的探测发生在 :745-760 凭据检查之前、`detect_ssh_auth_sources` 之前；探测只看 host 字符串的原始 DNS。
- 候选解析（remote_runner.py:68-118）对每一行都不做 `parse_ssh_config` 别名展开；`ssh_alias` 字段仅写配置/存 config_store（app.py:782-783、913），**从不参与 host 解析与探测**。只有 `resolve_ssh_profile` 在单条 hint 时才查 config（ssh_utils.py:126-138）。
- 用户自有机器/轮换机若以 `~/.ssh/config` 别名管理（ssh papercloud 可用），别名落在探测阶段就成了不可解析的裸主机名 → 报不可达。
- 另外「凭据缺失+主机不可达」时先报不可达而非缺凭据（探测在 login_methods 判断前），把用户引向排查网络。
- 最小修复：探测前先对每个候选做 config 别名展开（HostName/User/Port/IdentityFile），并把 login_methods 检查提到探测前（无任何凭据先报「缺凭据」）。

**R4（P1）TCP 可达 ≠ SSH 可用，且不向后回退**
- remote_runner.py:719-724 只取 `reachable[0]`，:788 起的连接失败重试仅针对同一主机，不尝试下一台 TCP 可达候选。某候选端口开着但非 SSH 服务（AutoDL 换机后旧端口可能被别的服务占用）会当场被选中，随后进入 3×2 秒重试与模糊的「远程执行失败」。
- 最小修复：把「选机」改为逐候选做短超时 paramiko 握手（~4s），失败继续下一候选，握手通过才正式执行。

**R5（P1）「测试 SSH 连接」按钮与提交链路是两套逻辑，且测的不是用户填的主机**
- ssh_utils.py:278-279：有 alias 时直接 `ssh -T <alias>`，完全忽略表单里的 host/user/port/key；而默认 alias 恒为 "papercloud"（app.py:695、809）。用户把真实 AutoDL 地址填进 ssh_target/主机框后点「测试」，测到的是旧 alias 或 ~/.ssh/config 里过期的 papercloud 条目。
- app.py:675 主机框默认值 `my-server.example.com` 非空（truthy），app.py:804-806 的 `(cloud_host or default_cloud_host)` 令解析出的真主机只在空值时生效 → 只填 ssh_target 时测试按钮会去连占位域名，必失败。
- 提交链路则用 paramiko 直连解析后的 host（remote_runner.py:766-790）→ 测试失败、提交却可能成功，或反之，两个按钮结论互相矛盾。
- 最小修复：测试逻辑与提交链路共用同一函数；未显式选择 alias 时优先按 host/user/password 直连。

**R6（P2）默认值三方打架（root/ubuntu、id_rsa/id_ed25519）**
- app.py:860 提交路径硬编码兜底 `"ubuntu"`，而 UI 默认 root（app.py:681、694），候选默认也是 root（app.py:874），ssh_utils 渲染 config 默认 root（ssh_utils.py:196）→ 用户清空用户名后认证失败方向错误；`detect_remote_workdir` 还按 root/其他分支决定 `/root/autodl-tmp` 还是 `/home/ubuntu`（remote_workdir.py:44-52）。
- 私钥默认同样三处不一致：app.py:861 兜底 `~/.ssh/id_rsa`，app.py:780-781 默认用自动生成的 id_ed25519，ssh_utils.py:200 config 默认 id_ed25519，而 `detect_ssh_auth_sources` 又把 id_rsa 排在 id_ed25519 前（remote_runner.py:202-218 的 key_candidates 顺序）→ 有 id_rsa 文件时永远优先试它。

**R7（P2）Windows 路径/换行/引号**
- ssh_utils.py:17 `shlex.split(target)` 默认 posix=True，把 `C:\Users\me\.ssh\key` 的反斜杠吞成 `C:Usersme.sshid_ed25519` → `-i` 路径失效；`parse_ssh_candidates` 的 ssh 分支（remote_runner.py:81-89）也不解析 `-i`。需 `shlex.split(posix=False)`（Windows）或在词元内单独检索 `-i`。

**R8（P2）多候选串行耗时与重复探测**
- remote_runner.py:719 对 N 个候选串行各 3 秒；:727 对单候选还把 self.host 再探测一遍（多耗 3 秒）。多台死机/占位符时提交按钮最长空转 3N 秒后才报错。

### 二、「填了正确信息却被判不可达」Top 5 假设与验证

1. **端口/尾缀污染 host**（代码级证据最强）。验证：`python -c "from paper_repro_app.remote_runner import parse_ssh_candidates as p; print(p(['root@connect.cqa1.seetacloud.com -p 38662']))"` —— 若 host 含 ` -p 38662` 即实锤；再查任务 DB/日志里 `tried` 串。
2. **3 秒 TCP 探测假阴性**。验证：PowerShell `Measure-Command { Test-NetConnection connect.cqa1.seetacloud.com -Port 38662 }`；计时 >3s 即实锤。把 remote_runner.py:719 的 timeout 临时改 10 秒复测即可确认。
3. **别名/ssh_config 未参与探测**。验证：`ssh -G papercloud` 能解析出 HostName，而 `parse_ssh_candidates(['papercloud'])` 返回裸名、`probe_host('papercloud',…)` DNS 失败。
4. **测试按钮/占位主机干扰**。验证：只填 ssh_target 后点「测试 SSH 连接」，看 st.error 里的主机名是否为 `my-server.example.com`（app.py:675/804-806 已锁定该行为）。
5. **实例真未开机或端口已过期**（非代码缺陷，AutoDL 每次开机换地址端口）。验证：手动 `ssh -p <当前控制台端口> …` 是否可达；对同一主机跑 `inject_public_key` 看错误分类是否进入认证诊断而非「不可达」。

### 三、冗余函数与不一致命名（可删可并）

- **PEM 写盘逻辑三份拷贝**：ssh_utils.ensure_ssh_key_file（141-158，目录 `paper_repro_generated`）、RemoteRunner.normalize_ssh_key_reference（183-199，目录 `auto_generated`）、模块级 `_resolve_key_file`（980-1005，目录 `auto_generated`）。应合并为一份，remote_runner 直接 import。
- **两套连接串解析器规则漂移**：ssh_utils.parse_ssh_target（11-60）vs remote_runner.parse_ssh_candidates（68-118），对 `-p38662` 紧贴、尾部 `-p`、默认 user 的语义互不一致，是 R1 的温床。
- **`abs(hash(value))` 做持久化文件名**（ssh_utils.py:150、remote_runner.py:192/990）：Python 字符串 hash 每进程随机（PYTHONHASHSEED），跨重启对同一粘贴 PEM 生成不同文件名 → 目录下垃圾密钥文件累积；应用内容 sha1 命名。
- **execute 中 self.host 二次探测**（remote_runner.py:724-728）与主探测重复。
- `resolved_key=key_candidates[0]`（remote_runner.py:205-216 顺序偏好）与 UI 实际生成密钥（id_ed25519）语义不一致。

### 四、81 个测试覆盖盲区（检测链路无真机的单测方法）

- tests/test_auto_hosts.py 仅覆盖 `parse_ssh_candidates` 5 个 happy-path；`probe_host` 0 覆盖；`RemoteRunner.execute` 探测/选机段 0 覆盖（tests/test_basic.py:623 只测取消前置分支）。合计 grep 得 81 个测试与「81 全绿」吻合，但检测主链路裸奔。
- 建议的单测配方（全部 mock，不连真网）：
  1. `monkeypatch` socket.create_connection 模拟可达/超时/拒连/慢速（sleep>3s 复现 R2），断言探测与消息分类；
  2. `monkeypatch` paramiko.SSHClient 返回认证异常，构造 `task["hosts"]` 多候选，断言：首候选 TCP 通但握手败→回退第二候选（现行为会失败，即为回归测试）；
  3. 无任何凭据 + 可达主机 → 断言返回「缺凭据」而非「不可达」（先于探测）；
  4. 解析一致性：`user@host -p 38662`、`ssh -p38662 root@host` 紧贴式、别名行、Windows `-i C:\...` 路径，断言 `parse_ssh_candidates` 与 `parse_ssh_target` 结果一致（现二者矛盾，测试即红灯）；
  5. `resolve_ssh_profile` 别名+fallback+key 合并优先级（tests/test_basic.py:115/132 只测了 parse_ssh_config 与 write_ssh_profile 单体）；
  6. `test_ssh_connection` 无系统 ssh 依赖的分支测试（monkeypatch subprocess.run）。

### 结论

代码证据指向：R1（候选二次解析污染 host）与 R2（3 秒探测）是「信息正确却判不可达」最可能的两个代码级根因；R3/R4 使其在别名、凭据缺失、端口占用场景下继续误报并给出无差别文案。修复优先级 R1>R2>R3，随后统一解析器与测试/执行两条链路，即可消除绝大多数误导。另检出 1 处 UI 约束违规：remote_runner.py:1060 注入成功消息含 `✅` emoji，经 `st.success` 上屏（app.py:826 展示路径），需移除。