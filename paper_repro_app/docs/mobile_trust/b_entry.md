研究报告已写入 `b_entry.md`（约 2200 字，两节 ## 决策 / ## 可执行变更，无 emoji）。要点回顾：

**决策**
- **D1 常开**：采纳，范围限 lan 档 + 开机自启（Windows shell:startup 放最小化启动器调 `start_app.bat --expose lan --no-browser`），口令门强制兜底；公网 tunnel 档维持按需手动（依赖云机计费/URL 易变），不做常开。
- **D2 手机入口**：主屏快捷方式（iOS/Android 步骤）为最高优先零依赖方案；应用内认证后加「手机直达」卡（可复制地址+主屏指引+打不开三分法）；**QR 默认不做**（外网 API/新依赖、场景错配，文字兜底足够）。
- **D3 PWA 终裁**：**不做真 PWA，采纳纯主屏快捷方式**。SW/manifest 需 https，lan 档必不合格；tunnel 档 AutoDL URL 是否 https 未实测 → 给出两步验证法（手机看地址栏锁）；即便 https，作用域/多源/离线收益≈0 使成本不划算，真 PWA 仅作 https 实测后的搁置选项。
- **D4 多开交互**：常开实例占 8505 后一切再启动都命中 `is_port_in_use` 只开浏览器不双开（现状已成立）；tunnel 可直接复用常开实例（0.0.0.0 亦监听回环、口令门仍生效）；"未跑"提示不靠服务端探测，靠直达卡三分法文案+自启兜底。

**可执行变更**：P0-1 start_app.py 加 `--no-browser`；P0-2 新增 autostart_install/uninstall.bat（注意 start_app_remote.bat 不透传参数，须直调 start_app.bat）；P1-3 app.py 手机直达卡；P1-4 GUIDE.md 增 G-8；P2-5 口令强度提示。并列出不做清单防蔓延。

**方法说明**：本会话无 web 工具，外部唯一未实测变量（AutoDL URL 协议）按任务要求以"两步验证法"处理而非断言；其余结论全部锚定于已核读的项目代码文件（start_app.py/access_gate.py/app.py/tunnel_keepalive.py 等）。