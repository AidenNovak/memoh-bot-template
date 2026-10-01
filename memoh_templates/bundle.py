"""Deterministic native Memoh backup bundles for creating a new bot."""
import gzip
import hashlib
import io
import json
import tarfile
import uuid
import zipfile
from .catalog import render, resolved_settings


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def bundle(template, parameters=None, bindings=None):
    workspace = io.BytesIO()
    with gzip.GzipFile(fileobj=workspace, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as tar:
            raw = render(template, parameters).encode()
            # Upstream untarGzDir roots extraction at /data; archive names are
            # relative to that directory, without an extra data/ prefix.
            info = tarfile.TarInfo("AGENTS.md")
            info.size, info.mode, info.mtime, info.uid, info.gid = len(raw), 0o640, 0, 0, 0
            tar.addfile(info, io.BytesIO(raw))
    bot_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/AidenNovak/memoh-bot-template/" + template["id"]))
    entries = {"bot/profile.json": json_bytes({"id": bot_id, "name": template["id"], **template["profile"]}),
               "bot/settings.json": json_bytes(resolved_settings(template, bindings)),
               "workspace/data.tar.gz": workspace.getvalue()}
    manifest = {"schema_version": 1, "app": "memoh", "exported_at": "2026-10-01T00:00:00Z",
                "source_bot_id": bot_id, "source_bot_name": template["id"],
                "options": {"sections": ["settings", "workspace"]},
                "entries": [{"path": k, "type": {"bot/profile.json": "bot_profile", "bot/settings.json": "bot_settings"}.get(k, "file")} for k in entries],
                "checksums": {k: hashlib.sha256(v).hexdigest() for k, v in entries.items()},
                "warnings": ["原创角色模板；默认不含模型与服务商配置，新建后需选择本实例的聊天模型。", "覆盖已有 Bot 请优先使用本仓库 apply 或本地选择页，以保留现有模型、记忆和工作区文件。"]}
    entries["manifest.json"] = json_bytes(manifest)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, content in entries.items():
            info = zipfile.ZipInfo(name, (2026, 10, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name.endswith(".tar.gz") else zipfile.ZIP_DEFLATED
            info.external_attr = 0o640 << 16
            archive.writestr(info, content)
    return out.getvalue()
