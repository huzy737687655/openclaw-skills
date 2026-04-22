#!/usr/bin/env python3
"""
req_list.py — 查询需求列表
"""
import argparse
import json
import os
import subprocess
import sys

DB_FILE_ID     = "4xGJbDenmxMrRgWLhxVY1x64KCEum7ZGC"
SHEET_OVERVIEW = 10
MCPORTER_CONFIG = os.path.join(os.path.dirname(__file__), "../../wps-cli/mcporter.json")

def mcpcall(tool, **kwargs):
    args = ", ".join(f"{k}: {json.dumps(v)}" for k, v in kwargs.items())
    cmd = ["mcporter", "--config", MCPORTER_CONFIG, "call", f"{tool}({args})"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"ERROR: {r.stderr}", file=sys.stderr); sys.exit(1)
    return json.loads(r.stdout.strip())

def main():
    parser = argparse.ArgumentParser(description="查询需求列表")
    parser.add_argument("--status", default="", help="按状态筛选（可选）")
    args = parser.parse_args()

    r = mcpcall("wps365.dbsheet.list_records",
        path_params={"file_id": DB_FILE_ID, "sheet_id": SHEET_OVERVIEW},
        body={"page_size": 200, "text_value": "text"})

    if r.get("code") != 0:
        print(f"❌ 查询失败: {r}", file=sys.stderr); sys.exit(1)

    records = r["data"]["records"]
    if not records:
        print("📋 暂无需求记录")
        return

    # 筛选
    results = []
    for rec in records:
        fields = json.loads(rec["fields"]) if isinstance(rec["fields"], str) else rec["fields"]
        if args.status and fields.get("当前状态") != args.status:
            continue
        results.append(fields)

    if not results:
        print(f"📋 无符合条件的需求（状态={args.status}）")
        return

    print(f"📋 需求列表（共 {len(results)} 条{'，状态='+args.status if args.status else ''}）\n")
    for i, f in enumerate(results, 1):
        name   = f.get("需求名称", "—")
        status = f.get("当前状态", "—")
        date   = f.get("需求提出时间", "—")
        ezone  = f.get("Ezone卡片", "")
        print(f"{i}. 【{status}】{name}  ({date})")
        if ezone:
            print(f"   Ezone: {ezone}")

if __name__ == "__main__":
    main()
