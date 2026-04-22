#!/usr/bin/env python3
"""
req_get.py — 获取单条需求详情
"""
import argparse
import json
import os
import subprocess
import sys

DB_FILE_ID     = "4xGJbDenmxMrRgWLhxVY1x64KCEum7ZGC"
SHEET_OVERVIEW = 10
SHEET_DETAIL   = 12
MCPORTER_CONFIG = os.path.join(os.path.dirname(__file__), "../../wps-cli/mcporter.json")

def mcpcall(tool, **kwargs):
    args_str = ", ".join(f"{k}: {json.dumps(v)}" for k, v in kwargs.items())
    cmd = ["mcporter", "--config", MCPORTER_CONFIG, "call", f"{tool}({args_str})"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"ERROR: {r.stderr}", file=sys.stderr); sys.exit(1)
    return json.loads(r.stdout.strip())

def find_record_fields(sheet_id, name):
    r = mcpcall("wps365.dbsheet.list_records",
        path_params={"file_id": DB_FILE_ID, "sheet_id": sheet_id},
        body={"page_size": 200, "text_value": "text"})
    if r.get("code") != 0:
        return None
    for rec in r["data"]["records"]:
        fields = json.loads(rec["fields"]) if isinstance(rec["fields"], str) else rec["fields"]
        if fields.get("需求名称") == name:
            return fields
    return None

def main():
    parser = argparse.ArgumentParser(description="获取需求详情")
    parser.add_argument("--name", required=True, help="需求名称")
    args = parser.parse_args()

    ov = find_record_fields(SHEET_OVERVIEW, args.name)
    det = find_record_fields(SHEET_DETAIL, args.name)

    if not ov and not det:
        print(f"❌ 未找到需求: {args.name}")
        sys.exit(1)

    print(f"\n📋 需求详情: {args.name}")
    print("=" * 50)

    if ov:
        print(f"  状态:        {ov.get('当前状态', '—')}")
        print(f"  Ezone卡片:   {ov.get('Ezone卡片', '—')}")
        print(f"  PRD文档:     {ov.get('PRD文档', '—')}")
        print(f"  需求提出时间: {ov.get('需求提出时间', '—')}")

    if det:
        print(f"  产品经理:    {det.get('产品经理', '—')}")
        print(f"  依赖方研发:  {det.get('依赖方研发', '—')}")
        print(f"  前端同学:    {det.get('前端同学', '—')}")
        print(f"  涉及项目:    {det.get('涉及项目', '—')}")
        print(f"  涉及配置:    {det.get('涉及配置', '—')}")
        print(f"  依赖层文档:  {det.get('依赖层文档', '—')}")
        print(f"  研发介入时间: {det.get('研发介入时间', '—')}")
        print(f"  提测时间:    {det.get('提测时间', '—')}")
        print(f"  上线时间:    {det.get('上线时间', '—')}")
        print(f"  需求日志:    {det.get('需求日志文档', '—')}")
        if det.get("备注"):
            print(f"  备注:        {det.get('备注')}")

if __name__ == "__main__":
    main()
