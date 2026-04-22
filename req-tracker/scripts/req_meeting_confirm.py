#!/usr/bin/env python3
"""
req_meeting_confirm.py — 处理用户对 pending 会议的回复，更新归档状态并追加日志
用法（由我解析用户回复后调用）：
  python3 req_meeting_confirm.py --replies '{"abc123":"节点亲和性调度","xyz456":"ignored"}'
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import _config as cfg

MCPORTER_CONFIG = os.path.join(os.path.dirname(__file__), "../../wps-cli/mcporter.json")
ARCHIVE_FILE    = os.path.join(os.path.dirname(__file__), "../references/meeting_archive.json")
DB_FILE_ID      = cfg.DB_FILE_ID
SHEET_DETAIL    = cfg.SHEET_DETAIL

def mcpcall(tool, **kwargs):
    args_str = ", ".join(f"{k}: {json.dumps(v)}" for k, v in kwargs.items())
    cmd = ["mcporter", "--config", MCPORTER_CONFIG, "call", f"{tool}({args_str})"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"ERROR: {r.stderr}", file=sys.stderr); sys.exit(1)
    return json.loads(r.stdout.strip())

def load_archive():
    if not os.path.exists(ARCHIVE_FILE):
        print("❌ 归档文件不存在，请先运行 req_meeting_sync.py", file=sys.stderr)
        sys.exit(1)
    with open(ARCHIVE_FILE) as f:
        return json.load(f)

def save_archive(data):
    with open(ARCHIVE_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def find_log_url(req_name):
    """从详情表找到需求日志文档 URL"""
    r = mcpcall("wps365.dbsheet.list_records",
        path_params={"file_id": DB_FILE_ID, "sheet_id": SHEET_DETAIL},
        body={"page_size": 200, "text_value": "text"})
    if r.get("code") != 0:
        return None
    for rec in r["data"]["records"]:
        fields = json.loads(rec["fields"]) if isinstance(rec["fields"], str) else rec["fields"]
        if fields.get("需求名称") == req_name:
            return fields.get("需求日志文档")
    return None

def find_doc_file_id(log_url, req_name):
    """通过搜索拿到文档 file_id"""
    r = mcpcall("ksc-mcp-wps.mcp_yundoc.search",
        body={"keyword": req_name, "page_size": 10})
    try:
        items = json.loads(r["result"]["content"][0]["text"]).get("items", [])
    except Exception:
        return None
    for item in items:
        f = item["file"]
        if f.get("link_url") == log_url:
            return f["id"]
    return None

def append_meeting_to_log(file_id, meeting_id, meeting_title, meeting_date, meeting_start, meeting_dur):
    """向日志文档追加会议摘要"""
    start_fmt = (meeting_start or "")[:16].replace("T", " ") if meeting_start else meeting_date
    dur_str   = f"（{meeting_dur}分钟）" if meeting_dur else ""
    content = f"""
### {meeting_date} 会议归档

| 字段 | 内容 |
|------|------|
| 会议主题 | {meeting_title} |
| 会议ID | {meeting_id} |
| 时间 | {start_fmt}{dur_str} |
| 关键结论 | 待补充 |

"""
    mcpcall("wps-dailyoffice.write_doc",
        action="append",
        file_id=file_id,
        content_markdown=content)

def main():
    parser = argparse.ArgumentParser(description="处理会议归档确认")
    parser.add_argument("--replies", required=True,
                        help='JSON map: {"会议ID":"需求名称"} 或 {"会议ID":"ignored"}')
    args = parser.parse_args()

    replies = json.loads(args.replies)
    archive = load_archive()

    archived_count = 0
    ignored_count  = 0
    errors         = []

    for meeting_id, decision in replies.items():
        if meeting_id not in archive["meetings"]:
            errors.append(f"⚠️  会议ID不存在: {meeting_id}")
            continue

        m = archive["meetings"][meeting_id]

        if decision.lower() in ("ignored", "忽略", "无关"):
            m["status"]   = "ignored"
            m["req_name"] = None
            ignored_count += 1
            print(f"  ⏭  忽略：{m['title']}")
            continue

        # 归档到需求
        req_name = decision
        log_url  = find_log_url(req_name)
        if not log_url:
            errors.append(f"❌ 未找到需求「{req_name}」的日志文档")
            continue

        file_id = find_doc_file_id(log_url, req_name)
        if not file_id:
            errors.append(f"❌ 无法定位「{req_name}」日志文档 file_id")
            continue

        append_meeting_to_log(
            file_id     = file_id,
            meeting_id  = meeting_id,
            meeting_title = m["title"],
            meeting_date  = m.get("date", ""),
            meeting_start = m.get("start"),
            meeting_dur   = m.get("duration")
        )

        m["status"]   = "archived"
        m["req_name"] = req_name
        archived_count += 1
        print(f"  ✅ 已归档：{m['title']} → 【{req_name}】")

    save_archive(archive)

    print(f"\n📊 本次归档：{archived_count} 条归档，{ignored_count} 条忽略")
    for e in errors:
        print(e)

if __name__ == "__main__":
    main()
