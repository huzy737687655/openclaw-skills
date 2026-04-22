#!/usr/bin/env python3
"""
req_update.py — 更新需求状态 / 关键时间节点
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _config as cfg
DB_FILE_ID     = cfg.DB_FILE_ID
SHEET_OVERVIEW = cfg.SHEET_OVERVIEW
SHEET_DETAIL   = cfg.SHEET_DETAIL
MCPORTER_CONFIG = os.path.join(os.path.dirname(__file__), "../../wps-cli/mcporter.json")

DATE_FIELDS = {"研发介入时间", "提测时间", "上线时间"}

def mcpcall(tool, **kwargs):
    args = ", ".join(f"{k}: {json.dumps(v)}" for k, v in kwargs.items())
    cmd = ["mcporter", "--config", MCPORTER_CONFIG, "call", f"{tool}({args})"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"ERROR: {r.stderr}", file=sys.stderr); sys.exit(1)
    return json.loads(r.stdout.strip())

def find_record(sheet_id, name):
    """按需求名称找记录 ID"""
    r = mcpcall("wps365.dbsheet.list_records",
        path_params={"file_id": DB_FILE_ID, "sheet_id": sheet_id},
        body={"page_size": 200, "text_value": "text"})
    if r.get("code") != 0:
        return None, None
    for rec in r["data"]["records"]:
        fields = json.loads(rec["fields"]) if isinstance(rec["fields"], str) else rec["fields"]
        if fields.get("需求名称") == name:
            return rec["id"], fields
    return None, None

def main():
    parser = argparse.ArgumentParser(description="更新需求状态或时间节点")
    parser.add_argument("--name",       required=True, help="需求名称")
    parser.add_argument("--status",     default="",    help="新状态")
    parser.add_argument("--date-field", default="",    help="要更新的时间字段（研发介入时间/提测时间/上线时间）")
    parser.add_argument("--date",       default="",    help="日期 YYYY-MM-DD，不填则用今天")
    args = parser.parse_args()

    if not args.status and not args.date_field:
        print("至少指定 --status 或 --date-field", file=sys.stderr)
        sys.exit(1)

    date_val = args.date or datetime.now().strftime("%Y-%m-%d")
    name = args.name

    # 更新总览表状态
    if args.status:
        ov_id, _ = find_record(SHEET_OVERVIEW, name)
        if not ov_id:
            print(f"❌ 总览表未找到需求: {name}", file=sys.stderr); sys.exit(1)
        r = mcpcall("wps365.dbsheet.update_records",
            path_params={"file_id": DB_FILE_ID, "sheet_id": SHEET_OVERVIEW},
            body={"records": [{"id": ov_id,
                               "fields_value": json.dumps({"当前状态": args.status}, ensure_ascii=False)}]})
        if r.get("code") == 0:
            print(f"✅ 状态更新为: {args.status}")
        else:
            print(f"❌ 状态更新失败: {r}", file=sys.stderr)

    # 更新详情表时间字段
    if args.date_field:
        if args.date_field not in DATE_FIELDS:
            print(f"❌ 不支持的时间字段: {args.date_field}，可选: {DATE_FIELDS}", file=sys.stderr)
            sys.exit(1)
        det_id, _ = find_record(SHEET_DETAIL, name)
        if not det_id:
            print(f"❌ 详情表未找到需求: {name}", file=sys.stderr); sys.exit(1)
        r = mcpcall("wps365.dbsheet.update_records",
            path_params={"file_id": DB_FILE_ID, "sheet_id": SHEET_DETAIL},
            body={"records": [{"id": det_id,
                               "fields_value": json.dumps({args.date_field: date_val}, ensure_ascii=False)}]})
        if r.get("code") == 0:
            print(f"✅ {args.date_field} 更新为: {date_val}")
        else:
            print(f"❌ 时间更新失败: {r}", file=sys.stderr)

if __name__ == "__main__":
    main()
