复核完成（只读核查，未运行测试）。关键事实均已从代码与规范交叉验证：expose 三档绑定逻辑（`start_app.py:276-351`）、口令门仅 session 态（`app.py:671-724` `_access_gate`，无任何 cookie/设备记忆）、`ai_client.py` 请求体仅 `model/messages/max_tokens(/stream)`、`make_dist.py` 分发面只含 FRIEND_GUIDE 常量与 `docs/troubleshoot/GUIDE.md`（二者现均无手机节）、全仓无 manifest/sw 且 README 无手机章节、`ui_theme.py` 已有 620px 移动 CSS、测试函数静态清点 8+7+5+6+4+8+43+6+5+6=98，与"98 测试绿"吻合。`docs/mobile_trust/` 尚不存在，本报告需落盘为 `docs/mobile_trust/mobile_packaging_review.md`（本会话无写权限，交 runtime 持久化）。

---

## 裁定

**不做任何原生打包；维持"电脑常驻 + 手机浏览器直达"架构，补一个"受信直达链接"把进入收敛为点一下图标。** 判据如下：

1. **需求形态错位**。本应用是"活页面控制台"——任务在云端/电脑跑，页面只做实时监控与指令下发（`app.py` 内 `@st.fragment(run_every=3.0)` 轮询 + WebSocket）。它的移动端痛点不是"缺一个 App 图标"，而是"每次冷开都要输口令"。离线价值为零，天然与 App/PWA 的缓存卖点相悖；真正要打包的是"免口令直达"能力，不是壳。
2. **PWA 前提不成立**。桌面默认仅回环；lan 档是明文 http（非安全上下文，SW/manifest 均不可注册，iOS/Android 一致）；tunnel 档走 AutoDL 自定义服务映射，https 与否未实测、且 URL 随实例漂移（`mobile_access_lead_spec` 已 P2 明载不实现）。即便实测为 https，Streamlit 无自脚本执行通道（CSP 剥 inline script、内部 index.html 模板不可承载体），SW 注册需要补 JS 静态文件与模板层，且对升级脆弱。投入产出比：只换得"全屏图标"这一个无关痛痒的收益。**真 PWA 不立项**。
3. **WebView 壳 APK 否决**：收益约等于一个图标窗口，与 Chrome 主屏书签等价；成本为安卓 SDK/Gradle/JDK/签名工具链 + 每次 LAN 地址漂移（换网络/换实例/换端口即失效，或需内置地址设置页）重打包或返工，个人侧载分发又与既有"口令门+零新依赖"姿态相冲。**iOS 无第三方壳**：唯一路径是 App Store 开发者账号+审核，与私有凭据的个人工具错配。**远程桌面类不适用**：控制的是整机桌面而非本应用，双端客户端+账号反而拖累"自主进入"。
4. **受信设备机制裁定**：Streamlit 无 Set-Cookie/持久会话通道，iframe 组件与父文档存储跨域隔离，唯一便利通道是 `st.query_params`。最小正解＝**受信直达链接**：首次口令通过后勾选"记住此设备"，生成高熵随机令牌，服务端哈希存 `~/.paper_repro_app/devices.json`（0600，无密码明文），拼为 `?tk=…` 直达链接；下次 `_access_gate` 读查询参数比对即放行、可一键吊销。成本约一个门内分支 + 两个单测，零依赖。令牌经明文 http 可嗅探的风险，由"令牌仅入口凭证 + 可吊销 + 口令门仍在"对冲并写入安全须知。
5. **三点诉求归位**：①"自主进入"＝开机自启（`start_app_remote.bat` 入 `shell:startup`，既有养机指引）+ 主屏直达；②"受信设备"＝上述令牌（不写明文、可吊销）；③"思考强度"是纯 AI 网关/UI 项（`chat_once/chat_stream` 现仅传 `model+max_tokens`；按 provider 差异映射：DeepSeek chat↔reasoner、Qwen `enable_thinking`、GLM thinking、OpenAI `reasoning_effort`），与打包形态正交，仅需提示 reasoner 长思考在移动网络下流量与耗时放大。

## 方案矩阵

| 形态 | 成本 | 裁定 |
|---|---|---|
| a. 浏览器书签/主屏快捷方式 | 现成（指南约 4 步文案，零代码） | **主路径**：LAN/tunnel 通用、零依赖 |
| b. 真 PWA（manifest+SW） | 需 https 实测 + 模板/静态层改造 | 否决主体；tunnel https 实测通过后仅做 manifest+图标的 P2 渐进增强，不阻塞 |
| c. Android WebView 壳 APK | SDK/Gradle/JDK/签名 + 地址漂移维护 | **否决**（收益≈书签，成本数倍，分发信任恶化） |
| d. iOS 壳 | App Store 账号+审核 | 否决（无侧载路径） |
| e. 远程桌面类 | 双端客户端+账号 | 不适用（控整机非本应用） |

**推荐组合**：主屏快捷方式（LAN/tunnel 通用）＋可选 tunnel https 下 manifest 渐进增强（P2）。受信直达链接卡（UI：首访口令页勾选信任→复制直达链接→提示加入主屏）作为唯一新增功能件。

**交付物**（约一个代码小版本）：①"手机使用"节——须落 `make_dist.py` 的 `FRIEND_GUIDE` 常量与 `docs/troubleshoot/GUIDE.md`（两者现均无手机节，且 zip 不含 README，故 README 同步为次）；四步：开机自启→手机打开 LAN/公网 URL→首访口令并生成直达链接→添加到主屏幕。②受信直达链接卡（复制按钮 + 吊销入口，安全须知注明令牌性质与吊销方法）。③`docs/mobile_trust/mobile_packaging_review.md` 落盘。

**验收**（真机 375px 流程 8 步）：口令页渲染→错口令拒→正口令过→"记住设备"出直达链接→复制并新开无痕会话以直达链接直进（免口令）→吊销后该链接失效→添加到主屏幕从图标再进→桌面 1366px 无回归 + make_dist 泄漏扫描零命中 + 新增令牌哈希/吊销/查询参数直通单测，98 测试基线全绿。

**结论**：不做 App、不做 PWA 主体；做"主屏直达 + 受信令牌"即可整体兑现"打包成手机也能用"，成本可控、零新依赖、可吊销可回退。

---
## Review
- Correct：98 测试数量与代码事实核对无误；expose 三档、口令门、ai_client 仅传 model/max_tokens、分发面无手机文案、全仓无 manifest/sw 等前提全部成立，裁定依据充分。
- Finding（P2，报告性）：`app.py` 监控 fragment 现为 `run_every=3.0`（`app.py:368/531`），与 lead spec 所述 2s/5s 口径不一致——新增省流量档/手机指南引用轮询频率时须按实际 3s 行文，避免文案与代码漂移。
- Merge verdict：OK with notes（本任务为评估裁定，无代码改动；上述 P2 供后续手机文案实施时核对）。