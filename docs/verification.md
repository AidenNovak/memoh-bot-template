# 验证记录

检查日期：2026-10-01。验证在 Memoh dev 的专用临时 Bot 上完成，结束后移除临时 Bot，确认原有 Bot 列表不变。没有修改现有用户 Bot 或生产服务。

## 真实 API

完整机器记录：[live.json](../verification/live.json)。

- 56/56 模板分别覆盖真实 Bot，回读资料、行为设置与实际 `/data/AGENTS.md`。
- 每次检查 MEMORY.md、PROFILES.md 与额外用户文件内容不变。
- 56/56 原生 `.memoh.zip` 通过 Memoh 原生导入预览，工作区恢复计划存在且无冲突。
- 恢复第一份自动备份后，原人格与资料一致。
- 实际原生导入芙莉莲，新建 Bot 的人格文件与渲染内容完全一致。
- 临时 Bot 清理完成；删除异步更新期间等待列表一致。

上游锁定提交与实际 dev 实例不是同一部署：本库覆盖当前上游29字段，dev 额外的 language 兼容字段未使用。此验证证明配置导入和回读有效，不是逐角色的模型输出评分，也不保证所有宿主模型都能同样演绎角色。

复现时需已有聊天模型与管理员权限，脚本只在自己的开发实例运行：

```sh
# 使用私有环境变量或已获取的访问令牌；不要把值写进 Git
MEMOH_URL=http://127.0.0.1:8080 python3 scripts/verify_live.py
```

脚本读取 `MEMOH_TOKEN` 或 `MEMOH_USERNAME` / `MEMOH_PASSWORD`，不会打印凭据。它会新建临时 Bot，完整验收后删除。

## 网页操作

[浏览器操作记录](../verification/browser-live.json)与[应用完成截图](../verification/gallery-applied.png)。

- 56 张模板卡片、搜索、角色详情、11 个可调参数。
- 1440px 桌面与390px手机布局无横向溢出。
- 真实登录后清空密码与令牌输入框。
- “预览覆盖”无修改；“应用并覆盖默认配置”一次点击成功。
- 自定义称呼与旅行节奏出现在实际人格文件。
- 模型 UUID 与额外工作区文件保留。
- 临时 Bot 已删除，截图省略实例 UUID 与本机备份路径。

截图：[桌面目录](../verification/gallery-desktop.png)、[调参](../verification/gallery-detail.png)、[手机](../verification/gallery-mobile.png)。浏览器脚本使用专用 Chrome 调试实例，不依赖 npm 包。

```sh
node scripts/verify_browser.mjs
# 真正应用验证：MEMOH_VERIFY_ENV 为本地私有 env 文件，包含 MEMOH_ADMIN_PASSWORD
MEMOH_VERIFY_ENV=/private/path/dev.env MEMOH_URL=http://127.0.0.1:8080 \
  node scripts/verify_browser_live.mjs
```

两个脚本均要求已启动8765端口选择页与9228端口的专用 Chrome。

## 自动门禁

18 个标准库测试覆盖模板完整性、参数渲染、全部导入包校验与 tar 路径、模型绑定继承、只读预览、备份权限、可选绑定清除、失败恢复和并发人格编辑保护。CLI 校验全部56模板、每份29个字段；还检查网页 JavaScript 语法与生成文件可复现。

```sh
python3 -m unittest discover -s tests -v
python3 -m memoh_templates validate
python3 scripts/build_catalog.py
git diff --exit-code
node --check web/app.js
```

提交后在干净检出上重复门禁。GitHub Actions 使用 Python 3.10 和3.12执行同样的校验，不连接任何 Memoh 实例，也不使用密钥。
