#!/usr/bin/env python3
"""Build reviewable presets from the handwritten catalog; no dependencies."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from memoh_templates.catalog import SETTING_FIELDS, render, validate
from memoh_templates.bundle import bundle

CATEGORIES = {"public-figures": "国际名人", "chinese-celebrities": "华语艺人与作家", "historical": "历史与文学人物",
              "anime": "动漫角色", "games": "游戏角色", "original": "原创互动玩法"}
PROFILES = {
    "engineer": ("high", 64000, 45, 2, 360, "先检验约束，再做最小实验；保留工程上下文"),
    "analyst": ("high", 56000, 40, 2, 450, "比较证据与代价，允许稍长的结论"),
    "editor": ("medium", 40000, 35, 2, 260, "快速指出关键问题，给短而具体的改稿"),
    "teacher": ("medium", 48000, 45, 1, 330, "一次解决一个误区，给用户练习空间"),
    "performer": ("low", 32000, 35, 3, 240, "保留舞台节奏与短互动，减少解释打断"),
    "quiet": ("low", 36000, 50, 0, 180, "短句、留白、较少主动追问"),
    "planner": ("medium", 40000, 40, 2, 280, "明确任务与期限，给可执行清单"),
    "companion": ("low", 48000, 50, 1, 220, "持续记住日常偏好，保持温和语气"),
    "playful": ("low", 36000, 45, 3, 200, "可选的小任务与轻松反馈"),
    "strategist": ("high", 64000, 40, 2, 430, "分支与对手回应较多，保留局势上下文"),
    "detective": ("high", 56000, 50, 1, 320, "线索前后一致，每轮只处理一个调查动作"),
    "coach": ("medium", 32000, 40, 2, 220, "最小行动、真实反馈与可达目标"),
    "worldbuilder": ("medium", 72000, 55, 2, 480, "长剧情需要状态与线索连续性"),
}


def param(label, default, **extra):
    kind = "integer" if type(default) is int else "string"
    return {"label": label, "type": kind, "default": default, **extra}


def build():
    styles={}
    for line in (ROOT/'catalog/conversation_style.psv').read_text().splitlines():
        if line and not line.startswith('#'):
            slug,lower,casual=line.split('|');styles[slug]=(lower,casual)
    sources = {}
    for row in (ROOT / "catalog/sources.tsv").read_text().splitlines():
        key, title, kind, url, note = row.split("\t")
        sources[key] = {"title": title, "kind": kind, "url": url, "checked_at": "2026-10-01", "note": note}
    (ROOT / "docs/research/sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n")
    catalog = []
    for line in (ROOT / "catalog/personas.psv").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        slug, name, category, icon, source, preset, identity, traits, scenario, flow, greeting, user, answer, knob, label, default, lore = line.split("|")
        effort, threshold, target, initiative, length, rationale = PROFILES[preset]
        binding = {"binding": "inherit"}
        settings = {key: copy.deepcopy(binding) for key in SETTING_FIELDS}
        settings.update(command_ui_language="auto", acl_default_effect="allow", timezone="Asia/Shanghai", reasoning_effort=effort,
                        compaction_enabled=True, compaction_threshold=threshold, compaction_target_percent=target,
                        persist_full_tool_results=False, show_tool_calls_in_im=False,
                        tool_approval_config={"enabled": True, "read": {"mode": "allow", "require_approval": False, "bypass_globs": [], "force_review_globs": []},
                                              "write": {"mode": "ask", "require_approval": True, "bypass_globs": ["/data/**", "/tmp/**"], "force_review_globs": []},
                                              "exec": {"mode": "ask", "require_approval": True, "bypass_commands": [], "force_review_commands": []}})
        parameters = {"user_name": param("用户称呼", "旅伴" if preset == "worldbuilder" else "朋友"),
                      "user_role": param("用户在场景中的身份", "自由选择的参与者"),
                      "language": param("回应语言", "跟随用户", enum=["跟随用户", "简体中文", "繁体中文", "English", "日本語"]),
                      "initiative": param("主动推进程度（0安静/3活跃）", initiative, minimum=0, maximum=3),
                      "response_length": param("每轮目标汉字数（软目标）", length, minimum=40, maximum=1200),
                      "warmth": param("亲近程度", "温和" if preset in ("quiet", "companion") else "自然", enum=["克制", "自然", "温和"]),
                      "humor": param("幽默频率", "低" if preset in ("analyst", "quiet", "detective") else "中", enum=["关闭", "低", "中", "高"]),
                      "spoiler_boundary": param("剧透边界", "仅作品开篇背景，关键转折先问用户" if category in ("anime", "games") else "重大背景由用户指定"),
                      "canon_mode": param("资料与创作界限", "原作背景+原创互动" if category in ("anime", "games") else "公开资料启发+原创场景"),
                      "interaction_mode": param("互动方式", "情景互动" if slug in ('trpg-gm','locked-room') else "日常聊天", enum=["情景互动", "日常聊天", "认真任务", "退出角色"]),
                      "roleplay_intensity": param("角色口吻强度（0普通/3沉浸）",1,minimum=0,maximum=3),
                      "conversation_style": param("聊天节奏", "沉浸剧情" if slug in ('trpg-gm','locked-room') else "自然聊天", enum=["自然聊天","按需分析","沉浸剧情"]),
                      knob: param(label, int(default) if default.isdigit() else default)}
        persona = {"identity": identity + " 使用模板设定进行角色演绎，不代表本人或官方。",
                   "personality": traits, "scenario": scenario + " 用户称呼为{{user_name}}，场景身份为{{user_role}}。",
                   "workflow": flow.split(";"), "greeting": greeting,
                   "examples": [{"user": user, "assistant": answer},
                                {"user": "把强度降一点，让我自己选。", "assistant":styles[slug][0]},
                                {"user": "今天不想跑流程，只想随便聊两句。", "assistant":styles[slug][1]}],
                   "lore": [{"keys": [name.split(" · ")[0], "背景", "设定"], "content": lore},
                            {"keys": ["玩法", "状态"], "content": "互动核心：" + rationale + "；设定资料与新剧情分开记录，不擅自增添用户未选择的关系。"}],
                   "memory": "只在用户同意时记住称呼、" + label + "偏好及当前进度；" + ("线索、角色资源与未完成分支作为虚构状态单独记录。" if preset in ("detective", "worldbuilder", "strategist") else "记录上一次实际完成的小步骤和用户明确表达的习惯。") + "不知道就问，不声称模板本身带有用户记忆。"}
        template = {"schema_version": 1, "id": slug, "name": name, "category": category, "icon": icon,
                    "description": scenario, "version": "1.0.0", "license": "AGPL-3.0-only",
                    "sources": [sources[source]], "popularity": {"basis": "原创玩法" if category == "original" else "官方资料与人工选材，非人气排名", "checked_at": "2026-10-01"},
                    "profile": {"display_name": name, "avatar_url": "", "timezone": "Asia/Shanghai", "is_active": True},
                    "settings": settings, "setting_rationale": rationale,
                    "parameters": parameters, "persona": persona,
                    "workspace": {"files": {"/data/AGENTS.md": "rendered persona"},
                                  "resource_limits": {"cpu_millicores": binding, "memory_bytes": binding, "storage_bytes": binding},
                                  "workdirs": [], "preserve": ["/data/MEMORY.md", "/data/PROFILES.md", "user files", "hooks", "skills"]},
                    "extensions": {"policy": "inherit; drafts are optional and never enabled by apply",
                                   "channels": [{"channel_type": "discord" if category in ("anime", "games", "original") else "telegram", "credentials": "configure in Memoh", "group_rule": "被点名或能够补充时回复"}],
                                   "mcp": [], "acl_rules": [], "schedules": [],
                                   "voice": {"tts_model_id": binding, "transcription_model_id": binding, "note": "按实例已有模型选择普通合成声线，不内置真人克隆"},
                                   "skills": [], "apps": [], "connectors": [], "agents": [], "hooks": binding,
                                   "sampling": {"temperature": "模型/Provider能力决定；当前Bot Settings无该字段", "top_p": "模型/Provider能力决定", "max_tokens": "模型配置决定"}}}
        if slug in ("kento-nanami", "arona", "cat-office", "lighthouse-radio", "march-7th"):
            template["extensions"]["schedules"] = [{"name": "模板可选日常回顾", "description": "用户在Memoh中选择时区和目标会话后启用", "pattern": "0 21 * * *",
                "enabled": False, "command": "使用当前角色口吻问今天的一件小事；不主动发往外部频道。", "max_calls": 7,
                "run_target": "new_session", "max_run_seconds": 300}]
        if category in ("anime", "games"):
            template["popularity"]["basis"] = "近期奖项覆盖与经典作品组合；不把系列热度等同单角排名"
            template["sources"].append(sources["tga" if category == "games" else "dandadan"])
        from memoh_templates.customization import defaults
        template['customization']=defaults(template)
        validate(template)
        directory = ROOT / "templates" / slug
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "template.json").write_text(json.dumps(template, indent=2, ensure_ascii=False) + "\n")
        (directory / "AGENTS.md").write_text(render(template))
        (directory / (slug + ".memoh.zip")).write_bytes(bundle(template))
        catalog.append({k: template[k] for k in ("id", "name", "category", "icon", "description", "parameters", "popularity")})
    (ROOT / "web/catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
    lines = ["# 模板目录", "", "所有首句、示例和游戏流程均为原创；点击名称查看配置，点击导入包下载后可通过 Memoh 的 Bot 导入界面新建。覆盖已有 Bot 请用本地选择页或 `apply`。", ""]
    for category, label in CATEGORIES.items():
        lines += [f"## {label}", "", "| 模板 | 玩法 | 原生导入包 |", "| --- | --- | --- |"]
        for t in catalog:
            if t["category"] == category:
                lines += [f"| [{t['icon']} {t['name']}](../templates/{t['id']}/template.json) | {t['description']} | [下载](../templates/{t['id']}/{t['id']}.memoh.zip) |"]
        lines += [""]
    (ROOT / "docs/catalog.md").write_text("\n".join(lines).rstrip() + "\n")
    print(f"Built {len(catalog)} templates, {len(sources)} research sources, {len(SETTING_FIELDS)} settings each")


if __name__ == "__main__":
    build()
