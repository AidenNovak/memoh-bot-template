# 上游 Bot 设定研究

检查日期：2026-10-01。上游为 [`felinics/Memoh`](https://github.com/felinics/Memoh)，锁定 [`1bfb42154e09efacd34f68898ceaab78c10c85f3`](https://github.com/felinics/Memoh/commit/1bfb42154e09efacd34f68898ceaab78c10c85f3)。本仓库独立维护模板，不修改上游或现有客户端。

| 需求 | 当前机制 | 本库落实 |
| --- | --- | --- |
| 持久人格与口吻 | 工作区 `/data/AGENTS.md` | 渲染角色、流程、首句、原创示例、世界设定和参数 |
| 长期记忆 | `MEMORY.md`、`PROFILES.md` 及实例 Memory Provider | 写入记忆约定，沿用既有记忆文件与 Provider |
| Bot 身份 | `bots.UpdateBotRequest` | 覆盖 display_name、avatar_url、timezone、is_active；默认保留 name、metadata，可通过customization.profile修改 |
| 行为、模型与运行时 | `settings.UpsertRequest`，29 项 | 完整列出；可携带本实例绑定或选择 inherit |
| 工作区编辑 | `GET container/fs/read`、`POST container/fs/write` | 回读 revision 后以 expectedRevision 写入 |
| 原生导入 | `POST /bots/backup/import`，multipart file | 生成 schema v1 的 `.memoh.zip` |
| 覆盖已有 Bot | 资料、Settings 与文件编辑 API | 自动备份，覆盖，回读；失败时尝试恢复 |
| 工具、定时任务、频道等 | 分立 API 与 Supermarket | 完整请求字段列入 customization，默认inherit，显式apply时应用；授权/重建入口单列 |

依据代码：

- [工作区默认人格](https://github.com/felinics/Memoh/blob/1bfb42154e09efacd34f68898ceaab78c10c85f3/templates/workspace/AGENTS.md)、[Bot 类型](https://github.com/felinics/Memoh/blob/1bfb42154e09efacd34f68898ceaab78c10c85f3/internal/bots/types.go)。
- [Settings 请求](https://github.com/felinics/Memoh/blob/1bfb42154e09efacd34f68898ceaab78c10c85f3/internal/settings/types.go)、[工作区文件接口](https://github.com/felinics/Memoh/blob/1bfb42154e09efacd34f68898ceaab78c10c85f3/internal/handlers/filemanager.go)。
- [备份 schema](https://github.com/felinics/Memoh/blob/1bfb42154e09efacd34f68898ceaab78c10c85f3/internal/botbackup/types.go)、[导入实现](https://github.com/felinics/Memoh/blob/1bfb42154e09efacd34f68898ceaab78c10c85f3/internal/botbackup/import.go)、[工作区 tar 根路径](https://github.com/felinics/Memoh/blob/1bfb42154e09efacd34f68898ceaab78c10c85f3/internal/workspace/dataio.go)。
- [OpenAPI 服务路径](https://github.com/felinics/Memoh/blob/1bfb42154e09efacd34f68898ceaab78c10c85f3/internal/handlers/swagger.go)：`/api/swagger.json`；本库先读取实例合约再修改。
- [推理能力选项](https://github.com/felinics/Memoh/blob/1bfb42154e09efacd34f68898ceaab78c10c85f3/internal/reasoning/options.go)：模型返回 `supported`、`can_disable`、`efforts`、`default_effort`，默认导入按真实能力调整，不保证所有模型支持所有档位。

原生包含 `manifest.json`、`bot/profile.json`、`bot/settings.json` 和 `workspace/data.tar.gz`。tar 中的 `AGENTS.md` 相对 `/data`，不能再加 `data/` 前缀。manifest 带 SHA-256 校验值，不带服务商、聊天记录或用户资料。

人格框架也参考 [SillyTavern 的官方 Character Design 文档](https://github.com/SillyTavern/SillyTavern-Docs/blob/main/Usage/Characters/characterdesign.md)：描述、性格、场景、首句、示例与世界设定。这里将其渲染到 Memoh 的工作区人格文件；SillyTavern 的 JSON 或 PNG 角色卡不是 Memoh 原生导入文件。本库没有复制社区卡片。

选材参考 45 个[来源](sources.json)。官方角色页用于背景，人物本人文章或机构资料用于公开形象；工作流程、游戏、对白和可调旋钮是本库设计。2026 动漫奖资料用于补充近期角色，官方游戏奖资料用于解释系列覆盖，不推导单角排名。

实际验收实例是 `vultr-sg` 的 Memoh dev。该实例 Settings 合约额外保留 `language` 字段；本库以当前上游29字段为基准，不使用这个兼容字段，也不依赖 fork 专有 API。
