# 参数与覆盖范围

每个 `templates/<id>/template.json` 列出完整的上游 Settings 合约。覆盖入口实际发送具体值；`{"binding":"inherit"}` 是本库的占位语法，会被省略，不能直接发给 Memoh。模型与 Provider UUID 是实例资源，应从自己的 Memoh 选择。显式填写空字符串可能清除绑定。

## 人格与互动

选择页“调一调”支持 13 个参数：12 个通用项与一个角色专属项。修改后重新渲染实际写入的 `/data/AGENTS.md`，下载包也带同样的渲染结果。

| 参数 | 用途 | 可选或范围 |
| --- | --- | --- |
| user_name | 用户称呼 | 文本 |
| user_role | 用户在场景中的身份 | 文本 |
| language | 回应语言 | 跟随用户、简体中文、繁体中文、English、日本語 |
| initiative | 主动推进程度 | 0–3 |
| response_length | 每轮目标汉字数 | 40–1200，提示词软目标 |
| warmth | 亲近程度 | 克制、自然、温和 |
| humor | 幽默频率 | 关闭、低、中、高 |
| spoiler_boundary | 剧透边界 | 文本 |
| canon_mode | 资料与创作界限 | 文本 |
| interaction_mode | 互动方式 | 情景互动、日常聊天、认真任务、退出角色 |
| roleplay_intensity | 角色口吻强度 | 0–3，默认1，轻点角色细节 |
| conversation_style | 回应方式 | 自然聊天、按需分析、沉浸剧情 |
| 角色专属参数 | 如第一性原理强度、幕僚年代、旅行节奏、案件难度 | 各模板自带名称与默认值 |

人格含身份、性格、场景、三段互动流程、开场、三段原创对话、世界设定与记忆约定。回复长度、幽默与亲近程度由模型理解，不能保证逐字限长。记忆约定不会凭空带来用户记忆。

## 29 个上游 Settings 字段

对应 [锁定的 API 合约](research/upstream-contract.json) 与 [上游研究](research/upstream.md)。高级 JSON 编辑器和 CLI `--settings` 都可覆盖这些字段。

| 字段 | 类型 | 默认处理与用途 |
| --- | --- | --- |
| acl_default_effect | string | allow；未匹配规则的 ACL 默认效果；原有具体规则保留 |
| chat_acp_agent_id | string | inherit；ACP Agent 绑定 |
| chat_acp_project_mode | string | inherit；ACP 项目模式 |
| chat_acp_project_path | string | inherit；ACP 项目路径 |
| chat_model_id | string | inherit；聊天模型 UUID |
| chat_runtime | string | inherit；宿主运行时。外部 Agent 转 Native 时明确填 model |
| command_ui_language | string | auto；命令界面语言 |
| compaction_enabled | boolean | true；启用上下文压缩 |
| compaction_model_id | string | inherit；压缩模型 UUID |
| compaction_target_percent | integer | 按模板为 35–55；压缩目标百分比。0 为上游清除哨兵值 |
| compaction_threshold | integer | 按模板为 32000–72000；上下文 token 压缩阈值 |
| default_bot_agent_id | string | inherit；默认 Bot Agent UUID |
| discuss_probe_model_id | string | inherit；讨论探针模型 UUID |
| display_enabled | boolean | inherit；显示能力开关 |
| fetch_provider_id | string | inherit；网页读取 Provider UUID |
| image_model_id | string | inherit；图像模型 UUID |
| memory_provider_id | string | inherit；记忆 Provider UUID |
| overlay_config | object | inherit；Overlay 提供商配置 |
| overlay_enabled | boolean | inherit；Overlay 开关 |
| overlay_provider | string | inherit；Overlay 提供商 |
| persist_full_tool_results | boolean | 按模板；是否保留完整工具结果 |
| reasoning_effort | string | 按模板；默认应用会适配实际模型支持的档位，明确改值则按用户选择发送 |
| search_provider_id | string | inherit；搜索 Provider UUID |
| show_tool_calls_in_im | boolean | 按模板；即时消息中显示工具调用 |
| timezone | string | Asia/Shanghai；行为时区 |
| tool_approval_config | object | enabled、read、write、exec 及匹配列表，详见下文 |
| transcription_model_id | string | inherit；转录模型 UUID |
| tts_model_id | string | inherit；语音合成模型 UUID |
| video_model_id | string | inherit；视频模型 UUID |

工具策略默认启用：读取 allow；写入 ask，`/data/**` 与 `/tmp/**` 在 bypass_globs 内；执行 ask。三类均可选择 allow / ask / deny，配置 `require_approval`、bypass 与 force_review 的路径或命令列表。这是导入后 Bot 的工具权限，与模板选择页的覆盖按钮独立。

不同角色分配给 13 种行为方案，采用不同推理偏好、压缩阈值、压缩目标、工具结果保留及工具调用可见性。人格与专属参数每个角色不同；共享方案不意味着所有 Settings 都不同。

资料 `profile` 另含 display_name、avatar_url、timezone、is_active 四项，覆盖入口会应用全部四项。头像默认空，可在角色 JSON 中填入自己的地址。内部 name 与 metadata 默认保留；通过 customization.profile 可显式修改 name、metadata 及其他资料字段。id 是实例身份，不属于可改的配置。

## 完整 Bot 定制

每份模板的 `customization` 包含 **58 个上游接口配置面**，以及 Hooks、连接器绑定说明、模型采样说明，共61组。请求字段从锁定的 OpenAPI 及源码提取，含嵌套对象、必填项与枚举：[完整字段合约](research/configuration-contract.json)。13种渠道的凭据、路由和目标格式另见[渠道合约](research/channel-schemas.json)。

| 配置 | 模板中的键 | 应用方式 |
| --- | --- | --- |
| 显示名、内部名、头像、时区、活跃、metadata | profile | 一键应用 |
| 创建资料、ACL预设、等待工作区 | creation | CLI create 时应用 |
| 默认ACL效果、规则、用户权限、渠道管理员、所有者 | acl_default_effect、acl_rules、user_access、channel_managers、owner及更新项 | 一键应用 |
| 频道凭据、自身身份、路由、启用 | channels、channel_status、channel_平台名 | 一键应用；默认 disabled，不发消息 |
| MCP名称、传输、URL、headers、工具开关及OAuth元数据 | mcp、mcp_update | 一键应用；默认不连接 |
| Apps安装/更新、API Key授权、连接器开关 | apps、app_update、app_connector_credentials、connector_enabled | 一键应用；填本实例ID和环境引用 |
| 外部Agent与凭据 | agents、agent_update、agent_credentials | 一键应用；OAuth仍需合法授权 |
| 工作目录、CPU/内存/存储、额外文件 | workdirs、resource_limits、workspace_files | 一键应用；先创建目录内容，再注册目录 |
| 技能内容与管理动作 | skills、skill_actions | 一键应用；技能写入当前上游管理路径 |
| 定时任务与完整执行参数 | schedules、schedule_update | 一键应用；默认禁用，含运行时/模型/工作目录/时长/次数/目标会话 |
| 初始记忆、记忆更新 | memory、memory_update | 一键应用；需实例支持所选记忆服务 |
| 远程工作区、主目标、每目标工具审批 | workspace_remote、workspace_primary、workspace_tool_approval | 一键应用；使用已有运行时/目标ID |
| Hooks配置 | hooks | 写入 /data/.memoh/hooks.json，包含34种事件、条件、动作及错误/超时策略 |
| 容器镜像/GPU、MCP stdio、依赖版本、Git分支、ACP临时运行时 | container_creation、mcp_stdio、dependency_*、workdir_git_branch、acp_* | 列出完整请求，使用对应Memoh入口；会重建或运行进程，不在普通覆盖中自动执行 |
| OAuth与webhook登记 | app_connector_oauth、channel_webhook | 列出完整请求，通过Memoh授权/登记入口 |
| 语音文本/音色/格式/语言、采样 | tts_defaults、model_sampling | 请求级或Provider级参数；当前Bot Settings无独立采样字段 |

每组默认 `mode: inherit`，普通覆盖沿用实例已有资源。只将需要的组设为 `mode: apply`；选择页“完整Bot定制”编辑器和 CLI `--customization` 使用同一流程。名称相同的 MCP、任务、Agent、目录和ACL规则会更新原记录，重复应用不会不断新增。

```sh
python3 -m memoh_templates apply frieren --bot YOUR_BOT_UUID \
  --customization examples/customization.json --dry-run
# 检查预览后去掉 --dry-run 即可应用
```

[示例配置](../examples/customization.json)含资料metadata、用户偏好文件、笔记目录、禁用MCP、禁用任务与资源限制。每份模板另附全部字段的可编辑表单。`requests`可含多个请求；路径UUID放 `path_parameters`。不支持的实例版本、未知字段、错误类型和缺失的环境变量在修改前报错。

凭据写成 `{"env":"MEMOH_TELEGRAM_BOT_TOKEN"}`，由运行本地工具的进程读取环境变量。预览只显示扩展字段名，不输出凭据；空字符串默认省略，需要明确清空时写 `{"literal":""}`。环境变量不会自动从远程服务器读取。

## 原生导入与完整配方

原生包始终携带人格、可移植Settings和 `/data/.memoh/template/customization.json` 完整配方。开启的额外文件、技能、Hooks、MCP、ACL、频道、任务、资源限制和目录会写入原生支持的部分。环境引用保留为配方，不把运行环境的真实密钥打入下载包。其他接口配置随配方保留，通过本库apply或Memoh对应入口应用。

当前上游原生任务导入仅恢复基础字段和max_run_seconds，会丢失模型/运行时/目标会话等执行覆盖；完整任务请用apply。模型UUID是实例绑定，新建后仍需选模型。本库不是用户历史或全局Provider迁移工具。

## 备份与恢复

应用前保存资料、29项Settings、人格，以及开启定制项的原状态。`.backups/`目录权限700，文件600，不进入Git。开启扩展后备份可能含私有频道/MCP数据，应妥善保管。

应用后回读资料、Settings和人格；扩展回读比较可读取的配置字段，并在结果的customization_receipts列出实际验证字段。密钥和被上游隐藏的metadata不声称逐值验证。额外文件使用revision，并发修改后的文件不会被失败回滚覆盖。

失败时按已执行步骤补偿。已创建的MCP、任务、Agent、目录、ACL和普通权限记录可删除；原文件、技能、资料和资源上限可恢复。部分接口（记忆追加、技能管理动作、安装/更新App或授权等）没有通用可逆操作；OAuth凭据读接口会隐藏数据，不能靠回读恢复其完整密钥。发生这种情况工具会明确报告需按备份处理的项。超时写入可能结果未知，先检查Bot再重试。

```sh
python3 -m memoh_templates restore .backups/GENERATED_BACKUP.json
```

默认没有启用workspace_files或memory，所以MEMORY.md、PROFILES.md、其他用户文件和旧会话均保留；开启相关组即表示有意修改所指定内容。用新聊天会话体验人格最直接。
