# 验证记录

头像更新、配置复验与多轮测试日期：2026-10-02；早期模型回答对比日期：2026-10-01。实际API与聊天验证在vultr-sg的独立 `memoh-template-eval` 实例进行，服务端和Web均由上游 `1bfb42154e09efacd34f68898ceaab78c10c85f3` 构建。测试创建自己的临时Bot，结束后删除；保留四个演示Bot供继续体验。

## 真实 API

[完整机器记录](../verification/live.json)包含56/56模板实际覆盖、56/56原生导入预览、自动备份恢复和芙莉莲的实际原生导入。每次都回读资料、29个行为字段和 `/data/AGENTS.md`，确认MEMORY.md、PROFILES.md和额外用户文件保留，最后等待临时Bot的异步删除完成。

[完整定制验证](../verification/customization-live.json)测试了10组启用的配置：资料元数据、工作区文件、禁用MCP、定时任务、工作目录、资源限制、技能、Hooks、禁用ACL规则与禁用Agent。重复应用会复用已创建的记录ID，保留定时任务的执行参数；自动备份可以恢复该次测试中的修改。定制的原生包也经过实际预览和导入。

58个配置接口面已经按上游请求结构纳入模板，**本次没有逐一执行全部58个接口**。OAuth、构建时设置、交互式ACP与一次性语音参数等标为参考项，需在对应Memoh入口配置。模板的完整字段覆盖、工具可执行范围与本次实测范围分别见[配置文档](configuration.md)。

复现需已有聊天模型、管理员权限和自己的开发实例：

```sh
MEMOH_URL=http://127.0.0.1:8080 python3 scripts/verify_live.py
MEMOH_URL=http://127.0.0.1:8080 python3 scripts/verify_customization_live.py
```

使用 `MEMOH_TOKEN` 或 `MEMOH_USERNAME` / `MEMOH_PASSWORD`；完整定制脚本使用用户名与密码。凭据不输出。`MEMOH_VERIFY_REPORT_DIR` 可把两份报告写到检出目录之外，私有备份默认写入被忽略的 `.backups/`。

## 网页操作与真实回答

- 选择页：56张卡片、搜索、角色详情、13个人格参数和完整配置编辑器；1440px桌面与390px手机无横向溢出。
- [头像显示](../verification/avatar-ui.json)：56张选择页头像全部解码为384×384；四个演示Bot资料回读一致，内嵌图片在实际Memoh网页显示。原生导入与一键覆盖均验证头像字节，显示无需访问源图片站点。[头像总览](../verification/avatars-contact.png)与[逐图来源](avatars.md)可直接查看。
- [一次点击应用](../verification/browser-live.json)：登录后清空凭据输入框，预览无修改，实际覆盖成功；称呼和旅行节奏出现在人格文件，模型与用户文件保留，临时Bot清理完成。
- [原生Memoh聊天](../verification/memoh-ui.json)：从真实网页发送消息，等待新的用户消息和模型回答持久化，并确认回答显示在界面。没有用本地生成文字替代模型回答。
- 两个实际聊天模型，共90条公开回答；方法、原始记录和不足见[模型测试](model-evaluation.md)。
- [多轮测试](multiturn-evaluation.md)：追加6个Bot×2模型×8轮的96条原始回复，以及4段修订后复测的32条。每段固定一个会话，等待匹配的运行完成再回读持久化消息。两批单列，没有用成功复测覆盖失败回复。
- [多轮原生界面](../verification/multiturn-ui.json)：四段实际八轮会话逐句回读后截图，截图脚本不发送消息；结束后删除这批临时Bot。视频包含连续第4—7轮、16条可追溯原文节选。

截图：[桌面目录](../verification/gallery-desktop.png)、[调参](../verification/gallery-detail.png)、[手机](../verification/gallery-mobile.png)、[应用完成](../verification/gallery-applied.png)、[实际聊天](../verification/memoh-chat.png)。浏览器脚本使用专用Chrome调试实例，不依赖npm包。

```sh
node scripts/verify_browser.mjs
MEMOH_VERIFY_ENV=/private/path/dev.env MEMOH_URL=http://127.0.0.1:8080 \
  node scripts/verify_browser_live.mjs
MEMOH_WEB_URL=http://127.0.0.1:12883 node scripts/verify_memoh_ui.mjs
MEMOH_WEB_URL=http://127.0.0.1:12883 node scripts/verify_avatar_ui.mjs
MEMOH_WEB_URL=http://127.0.0.1:12883 node scripts/capture_multiturn_ui.mjs
```

前两个脚本需启动8765端口选择页和9228端口专用Chrome。后两个需在同一Chrome中登录独立Memoh网页，且已创建演示Bot。头像脚本读取现有演示对话，不发送新消息。私有env文件只需 `MEMOH_ADMIN_PASSWORD`，不提交到Git。

## 自动门禁与宣传素材

36个标准库测试覆盖模板完整性、参数渲染、强度0退出角色、原生包结构、56个独立头像的字节与署名、离线头像导入、模型继承、备份权限、失败恢复、并发编辑保护，以及完整定制的字段校验、环境引用、文件路径、重复应用、回读不一致、资源恢复、MCP包格式和定时任务嵌套参数。新增的证据测试拒绝跨会话、未完成、改写、跳轮和把工具标签从节选里藏掉，并核对原生截图的字节与会话记录。

```sh
python3 -m unittest discover -s tests -v
python3 -m memoh_templates validate
python3 scripts/build_catalog.py
git diff --exit-code
node --check web/app.js
```

提交后使用干净检出重复门禁，并顺序重跑真实API与网页操作。GitHub Actions在Python3.10和3.12执行离线测试、56模板校验、确定性重生成和JavaScript语法检查，不连接Memoh或使用密钥。

新版两分钟宣传片主要展示多轮真实回答，复用内置image_gen原创插画、对应头像与代码生成的原创音乐。编码在服务器受限任务中完成，1080p成片参数见[多轮渲染报告](../promo/multiturn-render-report.json)，原文来源、脚本与早期30秒影片见[宣传素材](../promo/README.md)。
