#!/usr/bin/env python3
"""
req_log.py — 向需求日志文档追加内容（会议记录、群聊摘要等）
"""
import argparse
import json
import os
import subprocess
import sys

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _config as cfg
DB_FILE_ID   = cfg.DB_FILE_ID
SHEET_DETAIL = cfg.SHEET_DETAIL
MCPORTER_CONFIG = os.path.join(os.path.dirname(__file__), "../../wps-cli/mcporter.json")

def mcpcall(tool, **kwargs):
    args_str = ", ".join(f"{k}: {json.dumps(v)}" for k, v in kwargs.items())
    cmd = ["mcporter", "--config", MCPORTER_CONFIG, "call", f"{tool}({args_str})"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"ERROR: {r.stderr}", file=sys.stderr); sys.exit(1)
    return json.loads(r.stdout.strip())

def find_log_url(name):
    r = mcpcall("wps365.dbsheet.list_records",
        path_params={"file_id": DB_FILE_ID, "sheet_id": SHEET_DETAIL},
        body={"page_size": 200, "text_value": "text"})
    if r.get("code") != 0:
        return None
    for rec in r["data"]["records"]:
        fields = json.loads(rec["fields"]) if isinstance(rec["fields"], str) else rec["fields"]
        if fields.get("需求名称") == name:
            return fields.get("需求日志文档")
    return None

def main():
    parser = argparse.ArgumentParser(description="向需求日志文档追加内容")
    parser.add_argument("--name",    required=True, help="需求名称")
    parser.add_argument("--content", required=True, help="要追加的 Markdown 内容")
    args = parser.parse_args()

    log_url = find_log_url(args.name)
    if not log_url:
        print(f"❌ 未找到需求「{args.name}」的日志文档链接", file=sys.stderr)
        sys.exit(1)

    print(f"📝 追加到日志文档: {log_url}")

    # 先找到文档 file_id
    r_search = mcpcall("ksc-mcp-wps.mcp_yundoc.search",
        body={"keyword": args.name, "page_size": 10})
    items = json.loads(r_search["result"]["content"][0]["text"]).get("items", [])
    file_id = None
    for item in items:
        f = item["file"]
        if f.get("link_url") == log_url or log_url.endswith(f.get("link_id", "___")):
            file_id = f["id"]
            break

    if not file_id:
        print(f"❌ 无法定位日志文档 file_id，URL: {log_url}", file=sys.stderr)
        sys.exit(1)

    r_write = mcpcall("wps-dailyoffice.write_doc",
        action="append",
        file_id=file_id,
        content_markdown=args.content)

    if r_write.get("success") or r_write.get("file"):
        print("✅ 内容已追加")
    else:
        print(f"⚠️  追加结果: {json.dumps(r_write, ensure_ascii=False)[:200]}")

if __name__ == "__main__":
    main()
