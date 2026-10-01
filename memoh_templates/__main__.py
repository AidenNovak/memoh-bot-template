import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from . import catalog
from .api import Client
from .apply import apply_template, restore
from .bundle import bundle


def read_object(path):
    return json.loads(Path(path).read_text()) if path else {}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Memoh 趣味 Bot 模板：浏览、导入、一键覆盖")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="浏览模板")
    listing.add_argument("--category")
    commands.add_parser("validate", help="检查完整目录和所有上游设置字段")
    for name in ("show", "export", "apply", "create"):
        sub = commands.add_parser(name)
        sub.add_argument("template")
        sub.add_argument("--parameters", help="人格参数覆盖 JSON 文件")
        sub.add_argument("--settings", help="实际 Memoh 设置/模型 UUID JSON 文件")
        if name == "export":
            sub.add_argument("--output", required=True)
        if name in ("apply", "create"):
            add_connection(sub)
            sub.add_argument("--backup-dir", default=".backups")
        if name == "apply":
            sub.add_argument("--bot", required=True, help="目标 Bot UUID")
            sub.add_argument("--dry-run", action="store_true")
    sub = commands.add_parser("restore", help="恢复 apply 自动保存的备份")
    add_connection(sub)
    sub.add_argument("backup")
    server = commands.add_parser("serve", help="启动本地模板选择页")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "list":
        for item in catalog.templates():
            if not args.category or args.category == item["category"]:
                print(f"{item['id']:24} {item['name']} — {item['description']}")
        return
    if args.command == "validate":
        items = catalog.templates()
        for item in items:
            catalog.validate(item)
        print(f"通过：{len(items)} 个模板，每个覆盖 {len(catalog.SETTING_FIELDS)} 个上游 settings 字段")
        return
    if args.command == "serve":
        from .server import serve
        serve(args.port, args.open)
        return
    if args.command == "restore":
        client = connect(args)
        state = read_object(args.backup)
        restore(client, state)
        print("已恢复 Bot " + state["bot_id"])
        return
    item = catalog.load(args.template)
    parameters, settings = read_object(args.parameters), read_object(args.settings)
    if args.command == "show":
        print(catalog.render(item, parameters))
    elif args.command == "export":
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(bundle(item, parameters, settings))
        print(str(out))
    else:
        client = connect(args)
        created = None
        if args.command == "create":
            if not settings.get("chat_model_id"):
                raise ValueError("新建 Bot 需要在 --settings 文件中指定本实例的 chat_model_id")
            created = client.request("POST", "/bots", {"name": item["id"] + "-" + __import__('uuid').uuid4().hex[:6],
                                                       **item["profile"], "wait_for_ready": True})
            bot_id = created["id"]
        else:
            bot_id = args.bot
        try:
            result = apply_template(client, item, bot_id, parameters, settings, args.backup_dir,
                                    getattr(args, "dry_run", False))
        except Exception:
            if created:
                try:
                    client.request("DELETE", "/bots/" + bot_id)
                except Exception:
                    print("新建 Bot 清理失败，请手工删除：" + bot_id, file=sys.stderr)
            raise
        print(json.dumps(result, ensure_ascii=False, indent=2))


def add_connection(parser):
    parser.add_argument("--url", default=os.getenv("MEMOH_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--username", default=os.getenv("MEMOH_USERNAME", "admin"))


def connect(args):
    client = Client(args.url, os.getenv("MEMOH_TOKEN", ""))
    if not client.token:
        client.login(args.username, os.getenv("MEMOH_PASSWORD") or getpass.getpass("Memoh 密码（不保存）："))
    return client


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, KeyError) as exc:
        print("错误：" + str(exc), file=sys.stderr)
        sys.exit(1)
