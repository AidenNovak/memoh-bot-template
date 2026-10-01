"""Overwrite persona and behavior, with local backup and compensation."""
import json
import copy
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from .api import APIError
from .catalog import SETTING_FIELDS, render, resolved_settings, validate

AGENTS_PATH = "/data/AGENTS.md"


def snapshot(client, bot_id):
    root = "/bots/" + quote(bot_id, safe="")
    profile = client.request("GET", root)
    settings = client.request("GET", root + "/settings")
    # Upstream omits empty optional bindings on reads. Keep their empty values in
    # backups so an explicitly added binding can be cleared by restore.
    for key in ("default_bot_agent_id", "chat_acp_agent_id", "chat_acp_project_path",
                "chat_acp_project_mode", "compaction_model_id", "discuss_probe_model_id", "overlay_provider"):
        settings.setdefault(key, "")
    settings.setdefault("overlay_config", {})
    try:
        file = client.request("GET", root + "/container/fs/read?" + urlencode({"path": AGENTS_PATH}))
    except APIError as exc:
        if exc.status != 404:
            raise
        # A 404 may mean no workspace, so require the file-manager root to work.
        client.request("GET", root + "/container/fs/list?" + urlencode({"path": "/data"}))
        file = None
    return {"schema_version": 1, "bot_id": bot_id, "profile": {k: profile.get(k, True if k == "is_active" else "") for k in ("display_name", "avatar_url", "timezone", "is_active")},
            "settings": {k: v for k, v in settings.items() if k in SETTING_FIELDS}, "agents": file,
            "created_at": datetime.now(timezone.utc).isoformat()}


def save_backup(state, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex + ".json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
    return path


def restore(client, state):
    root = "/bots/" + quote(state["bot_id"], safe="")
    errors=[]
    if state.get('customization_receipts'):
        from .customization import undo
        errors=undo(client,state['customization_snapshots'],state['customization_receipts'])
    # Do not include metadata: API reads intentionally scrub external-agent secrets.
    client.request("PUT", root, {k: v for k, v in state["profile"].items() if v is not None})
    payload = {k: v for k, v in state["settings"].items() if v is not None}
    # null/absent compaction target clears via the upstream zero sentinel.
    if state["settings"].get("compaction_target_percent") is None:
        payload["compaction_target_percent"] = 0
    client.request("PUT", root + "/settings", payload)
    if state["agents"] is None:
        try:
            client.request("POST", root + "/container/fs/delete", {"path": AGENTS_PATH})
        except APIError as exc:
            if exc.status != 404:
                raise
    else:
        client.request("POST", root + "/container/fs/write", {"path": AGENTS_PATH, "content": state["agents"]["content"]})
    if errors:raise RuntimeError('人格与行为已恢复；部分扩展需按备份处理：'+'; '.join(errors))


def apply_template(client, template, bot_id, parameters=None, bindings=None, backup_dir=".backups", dry_run=False, customizations=None):
    from .customization import plan as customization_plan, safe_plan, snapshot_actions, execute, undo, resolve
    template=copy.deepcopy(template)
    profile_section=(customizations or {}).get('profile',template.get('customization',{}).get('profile',{}))
    if profile_section.get('mode')=='apply':
        for request in profile_section.get('requests',[]):
            template['profile'].update({k:v for k,v in resolve(request).items() if k in template['profile']})
    validate(template)
    text = render(template, parameters)
    payload = resolved_settings(template, bindings)
    contract = client.contract()
    custom_actions=customization_plan(template,customizations,bot_id,contract)
    for action in custom_actions:
        if action['section']=='acl_default_effect':payload['acl_default_effect']=action['body']['default_effect']
    supported = contract["definitions"].get("settings.UpsertRequest", {}).get("properties", {})
    missing = set(payload) - set(supported)
    if missing:
        raise ValueError("实例版本不兼容，未修改任何内容；缺少设置：" + ", ".join(sorted(missing)))
    if "/bots/{bot_id}/container/fs/write" not in contract["paths"]:
        raise ValueError("实例缺少工作区文本写接口，未修改任何内容")
    before = snapshot(client, bot_id)
    if custom_actions:before['customization_snapshots']=snapshot_actions(client,custom_actions)
    if before["settings"].get("chat_runtime", "model") != "model" and "chat_runtime" not in (bindings or {}):
        raise ValueError("当前 Bot 使用外部 Agent；请用 --settings 明确选择 chat_runtime=model 和 chat_model_id，或使用 Native Bot")
    # Reasoning tiers depend on the selected model; a caller can explicitly bind
    # reasoning_effort. Otherwise use the model's advertised choice when available.
    warnings = []
    model_id = payload.get("chat_model_id", before["settings"].get("chat_model_id"))
    if model_id and "reasoning_effort" not in (bindings or {}):
        models = client.request("GET", "/models")
        items = models if isinstance(models, list) else models.get("items", models.get("data", []))
        model = next((m for m in items if m.get("id") == model_id), None)
        options = (model or {}).get("reasoning") or {}
        tiers = list(options.get("efforts", []))
        if options.get("can_disable"):
            tiers.append("disable")
        if tiers and payload.get("reasoning_effort") not in tiers:
            preferred = before["settings"].get("reasoning_effort")
            default = options.get("default_effort")
            payload["reasoning_effort"] = preferred if preferred in tiers else default if default in tiers else tiers[0]
            warnings.append("按目标模型支持的推理档位调整 reasoning_effort")
    plan = {"bot_id": bot_id, "template_id": template["id"], "profile": template["profile"], "settings": payload,
            "workspace_paths": [AGENTS_PATH], "warnings": warnings}
    if custom_actions:plan['customization']=safe_plan(custom_actions)
    if dry_run:
        return {"dry_run": True, "plan": plan}
    backup = save_backup(before, backup_dir)
    root = "/bots/" + quote(bot_id, safe="")
    settings_attempted = profile_attempted = file_attempted = False
    try:
        settings_attempted = True  # A timeout may occur after a committed write.
        client.request("PUT", root + "/settings", payload)
        profile_attempted = True
        client.request("PUT", root, template["profile"])
        write = {"path": AGENTS_PATH, "content": text}
        if before["agents"] and before["agents"].get("revision"):
            write["expectedRevision"] = before["agents"]["revision"]
        file_attempted = True
        client.request("POST", root + "/container/fs/write", write)
        if custom_actions:
            def record(receipts):
                before['customization_receipts']=receipts
                backup.write_text(json.dumps(before,ensure_ascii=False,indent=2))
            execute(client,before['customization_snapshots'],record)
        after = snapshot(client, bot_id)
        if after["agents"]["content"] != text:
            raise ValueError("工作区人格回读与模板不一致")
        for key, value in template["profile"].items():
            if after["profile"].get(key) != value:
                raise ValueError(f"Bot 资料回读不一致：{key}")
        for key, value in payload.items():
            if after["settings"].get(key) != value:
                raise ValueError(f"设置回读不一致：{key}")
        return {"bot_id": bot_id, "template_id": template["id"], "backup": str(backup), "verified": True, "warnings": warnings,
                "customization":safe_plan(custom_actions),"customization_receipts":before.get('customization_receipts',[])}
    except Exception as exc:
        rollback = []
        if before.get('customization_receipts'):
            rollback.extend(undo(client,before['customization_snapshots'],before['customization_receipts']))
        operations = []
        if settings_attempted:
            previous = {k: before["settings"][k] for k in payload if k in before["settings"] and before["settings"][k] is not None}
            if "compaction_target_percent" in payload and before["settings"].get("compaction_target_percent") is None:
                previous["compaction_target_percent"] = 0
            operations.append(lambda: client.request("PUT", root + "/settings", previous))
        if profile_attempted:
            operations.append(lambda: client.request("PUT", root, before["profile"]))
        if file_attempted and not (isinstance(exc, APIError) and exc.status == 409):
            def undo_file():
                try:
                    latest = client.request("GET", root + "/container/fs/read?" + urlencode({"path": AGENTS_PATH}))
                except APIError as read_error:
                    if read_error.status == 404:
                        return
                    raise
                # A failed write or a later user edit must never be overwritten.
                if latest["content"] != text:
                    return
                if before["agents"] is None:
                    client.request("POST", root + "/container/fs/delete", {"path": AGENTS_PATH})
                else:
                    data = {"path": AGENTS_PATH, "content": before["agents"]["content"]}
                    if latest.get("revision"):
                        data["expectedRevision"] = latest["revision"]
                    client.request("POST", root + "/container/fs/write", data)
            operations.append(undo_file)
        for operation in operations:
            try:
                operation()
            except Exception as undo:
                rollback.append(str(undo))
        raise RuntimeError(f"应用失败：{exc}。备份：{backup}。" + ("回滚失败：" + "; ".join(rollback) if rollback else "已恢复原设置。")) from None
