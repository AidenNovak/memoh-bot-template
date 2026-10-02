"""Deterministic native Memoh backup bundles for creating a new bot."""
import gzip
import hashlib
import io
import json
import tarfile
import uuid
import zipfile
import copy
import posixpath
import re
from .catalog import render, resolved_settings
from .customization import CONFIG, resolve, validate_body
from .avatars import image_bytes


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def bundle(template, parameters=None, bindings=None, customizations=None):
    sections = copy.deepcopy(template.get('customization', {}))
    for key, value in (customizations or {}).items():
        if key not in sections:
            raise ValueError('未知定制面：' + key)
        sections[key] = value
    profile = {"name": template["id"], **template["profile"]}
    files = {'AGENTS.md': render(template, parameters).encode()}
    # Keep the complete portable recipe, including environment references.
    # Native Memoh restores this file; apply reads the recipe through --customization.
    files['.memoh/template/customization.json'] = json_bytes(sections)
    if template.get('avatar'):
        files['.memoh/template/avatar.jpg'] = image_bytes(template['avatar'])
        files['.memoh/template/avatar-source.json'] = json_bytes(template['avatar'])
    native = {}
    options = ['settings', 'workspace']
    warnings = ["原创角色模板；默认不含模型与服务商配置，新建后需选择本实例的聊天模型。",
                "原生导入只恢复 manifest 中的部分；完整定制配方在 /data/.memoh/template/customization.json，通过 apply --customization 应用。"]
    mappings = {'mcp': ('mcp_connections', 'mcp'), 'acl_rules': ('acl_rules', 'acl'),
                'schedules': ('schedules', 'schedules'), 'workdirs': ('workdirs', 'workspace')}
    settings = resolved_settings(template, bindings)
    if settings.get('chat_model_id'):
        warnings[0]='原创角色模板；包含调用者显式指定的模型UUID，导入实例必须具有同一模型资源。'
    def has_binding(value):
        if isinstance(value, dict):
            return set(value) == {'env'} or any(has_binding(v) for v in value.values())
        return isinstance(value, list) and any(has_binding(v) for v in value)
    def file(path, content):
        normalized = posixpath.normpath(path)
        if not normalized.startswith('/data/') or normalized == '/data/AGENTS.md':
            raise ValueError('扩展文件必须位于 /data/，AGENTS.md 请通过人格参数修改')
        files[normalized[len('/data/'):]] = content.encode()
    for key, section in sections.items():
        if section.get('mode', 'inherit') == 'inherit':
            continue
        if section.get('mode') != 'apply':
            raise ValueError(key + ': mode 必须是 inherit 或 apply')
        for raw in section.get('requests', []):
            if has_binding(raw):
                warnings.append(key + ': 环境引用保留在配方中，原生导入不写入凭据；使用 apply 解析。')
                continue
            body = resolve(raw)
            if key in CONFIG['surfaces']:
                validate_body(body, CONFIG['surfaces'][key]['schema'], key)
            if key == 'profile':
                profile.update(body)
            elif key == 'workspace_files':
                file(body['path'], body['content'])
            elif key == 'hooks':
                file('/data/.memoh/hooks.json', json_bytes(body).decode())
            elif key == 'skills':
                for skill in body.get('skills', []):
                    match = re.search(r'^name:\s*[\"\']?([a-z0-9_-]+)[\"\']?\s*$', skill, re.M)
                    if not match:
                        raise ValueError('技能需要简单的 frontmatter name')
                    file(body.get('source_path') or '/data/skills/user/personal/' + match[1] + '/SKILL.md', skill.strip() + '\n')
            elif key in mappings:
                if key == 'schedules' and not settings.get('chat_model_id'):
                    warnings.append('schedules: 原生新建即使任务禁用也要求默认模型；未绑定模型时只保留配方，选模型后apply。')
                    continue
                filename, option = mappings[key]
                value = body
                if key == 'mcp':
                    value = {'name': body.get('name', ''), 'type': 'stdio' if body.get('command') else 'sse' if body.get('transport') == 'sse' else 'http',
                             'is_active': body.get('is_active', True), 'auth_type': body.get('auth_type', ''),
                             'config': {k: v for k, v in body.items() if k in ['command', 'args', 'env', 'cwd', 'url', 'headers']}}
                native.setdefault('bot/' + filename + '.json', []).append(value)
                if option not in options:
                    options.append(option)
            elif key == 'resource_limits':
                native['bot/workspace_resource_limits.json'] = body['resource_limits']
            elif key == 'channels' or key.startswith('channel_') and 'platform' in CONFIG['surfaces'].get(key, {}):
                platform = section.get('path_parameters', {}).get('platform')
                if not platform:
                    raise ValueError(key + ': 缺少 platform')
                native.setdefault('bot/channel_configs.json', []).append({'channel_type': platform, **body})
                if 'channels' not in options:
                    options.append('channels')
            else:
                warnings.append(key + ': 此项保留在完整配方中，通过 apply 或对应 Memoh 界面配置。')
    workspace = io.BytesIO()
    with gzip.GzipFile(fileobj=workspace, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as tar:
            # Upstream untarGzDir roots extraction at /data; archive names are
            # relative to that directory, without an extra data/ prefix.
            for name, raw in files.items():
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime, info.uid, info.gid = len(raw), 0o640, 0, 0, 0
                tar.addfile(info, io.BytesIO(raw))
    bot_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/AidenNovak/memoh-bot-template/" + template["id"]))
    entries = {"bot/profile.json": json_bytes({"id": bot_id, **profile}),
               "bot/settings.json": json_bytes(settings),
               "workspace/data.tar.gz": workspace.getvalue()}
    entries.update({k: json_bytes(v) for k, v in native.items()})
    manifest = {"schema_version": 1, "app": "memoh", "exported_at": "2026-10-01T00:00:00Z",
                "source_bot_id": bot_id, "source_bot_name": template["id"],
                "options": {"sections": options},
                "entries": [{"path": k, "type": {"bot/profile.json": "bot_profile", "bot/settings.json": "bot_settings"}.get(k, "file")} for k in entries],
                "checksums": {k: hashlib.sha256(v).hexdigest() for k, v in entries.items()},
                "warnings": warnings}
    entries["manifest.json"] = json_bytes(manifest)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, content in entries.items():
            info = zipfile.ZipInfo(name, (2026, 10, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name.endswith(".tar.gz") else zipfile.ZIP_DEFLATED
            info.external_attr = 0o640 << 16
            archive.writestr(info, content)
    return out.getvalue()
