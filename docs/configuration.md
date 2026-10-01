# 参数与覆盖范围

每个 `templates/<id>/template.json` 列出完整的上游 Settings 合约。覆盖入口实际发送具体值；`{"binding":"inherit"}` 是本库的占位语法，会被省略，不能直接发给 Memoh。模型与 Provider UUID 是实例资源，应从自己的 Memoh 选择。显式填写空字符串可能清除绑定。

## 人格与互动

选择页“调一调”支持 11 个参数：10 个通用项与一个角色专属项。修改后重新渲染实际写入的 `/data/AGENTS.md`，下载包也带同样的渲染结果。

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
| 角色专属参数 | 如第一性原理强度、幕僚年代、旅行节奏、案件难度 | 各模板自带名称与默认值 |

人格含身份、性格、场景、三段互动流程、开场、至少两段原创对话、世界设定与记忆约定。回复长度、幽默与亲近程度由模型理解，不能保证逐字限长。记忆约定不会凭空带来用户记忆。

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

资料 `profile` 另含 display_name、avatar_url、timezone、is_active 四项，覆盖入口会应用全部四项。头像默认空，可在角色 JSON 中填入自己的地址。Bot 内部 name、id 与 metadata 不改。

## 其他可配置面

这些字段完整展示模板适配范围，**不是覆盖按钮已安装的资源**：

| 配置面 | 本库表示 | 实际处理 |
| --- | --- | --- |
| 工作区资源 | workspace.resource_limits：CPU、内存、存储 | inherit；由实例管理员配置 |
| 工作目录 | workspace.workdirs | 空草稿；保留实例现状 |
| 频道与群聊 | extensions.channels | 推荐频道与回应规则；凭据在 Memoh 配置 |
| MCP、ACL、Apps、Connectors、Agents、Skills | extensions 中同名列表 | 空草稿；原有资源不增删 |
| 定时任务 | extensions.schedules | 部分角色含禁用草稿；需在 Memoh 单独创建和启用 |
| Hooks | extensions.hooks | inherit；原有工作区文件保留 |
| 语音 | extensions.voice | 沿用普通 TTS/STT 模型；不内置真人克隆声线 |
| temperature、top_p、max_tokens | extensions.sampling | 当前 Bot Settings 没有对应字段，按模型/Provider 能力配置 |

本库不是全量 Bot 迁移工具。原生导入包只含资料、可移植行为设置与人格文件；频道密钥、用户资料、历史与其他工作区内容不会进入包。Native 新建后需要选择聊天模型；已有 Bot 覆盖会沿用现有模型绑定。

## 备份与恢复

应用前保存目标资料、29 字段范围内的设置与原人格文件，备份目录 `.backups/`，文件权限 600，不纳入 Git。备份可能含你的自定义人格内容，应自行保管。

应用依次写 Settings、资料、人格，再回读验证。人格以 revision 检查并发编辑；写入失败时按已尝试的步骤恢复设置和资料，只在文件仍等于本次模板时恢复人格。失败回滚也可能失败，工具会报告原备份位置。手动 `restore` 是明确恢复旧配置的操作。

```sh
python3 -m memoh_templates restore .backups/GENERATED_BACKUP.json
```

工作区的 MEMORY.md、PROFILES.md 与其他文件原样保留；旧会话上下文也保留。新建聊天会话可更清楚地看到新角色行为。
