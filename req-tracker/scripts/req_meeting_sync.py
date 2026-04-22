#!/usr/bin/env python3
"""
req_meeting_sync.py — 拉取当天会议记录，与本地 archive 对比，列出未归档条目
用法：
  python3 req_meeting_sync.py          # 拉取今天
  python3 req_meeting_sync.py --date 2026-04-21  # 指定日期
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import _config as cfg

MCPORTER_CONFIG  = os.path.join(os.path.dirname(__file__), "../../wps-cli/mcporter.json")
ARCHIVE_FILE     = os.path.join(os.path.dirname(__file__), "../references/meeting_archive.json")
BATCH_SIZE       = 5

def mcpcall(tool, **kwargs):
    args_str = ", ".join(f"{k}: {json.dumps(v)}" for k, v in kwargs.items())
    cmd = ["mcporter", "--config", MCPORTER_CONFIG, "call", f"{tool}({args_str})"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"ERROR: {r.stderr}", file=sys.stderr); sys.exit(1)
    return json.loads(r.stdout.strip())

def load_archive():
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE) as f:
            return json.load(f)
    return {"meetings": {}, "last_sync": None}

def save_archive(data):
    os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)
    with open(ARCHIVE_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def purge_old(archive, keep_days):
    """清理超过 keep_days 天的记录"""
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    before = len(archive["meetings"])
    archive["meetings"] = {
        mid: m for mid, m in archive["meetings"].items()
        if m.get("date", "9999") >= cutoff
    }
    removed = before - len(archive["meetings"])
    if removed:
        print(f"  🗑  清理 {removed} 条超期记录（>{keep_days}天）")

def fetch_meetings(date_str):
    """拉取指定日期的会议列表，返回 [{id, title, start_time, duration_min}]"""
    # 构造当天 unix 秒时间范围（Asia/Shanghai UTC+8）
    tz8 = timezone(timedelta(hours=8))
    day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz8)
    start_ts = int(day.timestamp())
    end_ts   = int((day + timedelta(days=1)).timestamp())

    r = mcpcall("ksc-mcp-wps.mcp_meeting.list",
        body={"start_date_time": start_ts, "end_date_time": end_ts, "page_size": 50})

    # 解析响应
    try:
        content = r["result"]["content"][0]["text"]
        data = json.loads(content)
        items = data.get("items") or data.get("meetings") or []
    except Exception:
        items = []

    result = []
    for m in items:
        mid   = m.get("id") or m.get("meeting_id") or m.get("uuid", "")
        title = m.get("topic") or m.get("subject") or m.get("title", "（无主题）")
        start = m.get("start_time") or m.get("startTime", "")
        dur   = m.get("duration") or m.get("duration_minutes", 0)
        if mid:
            result.append({"id": str(mid), "title": title, "start": start, "duration": dur})
    return result

def main():
    parser = argparse.ArgumentParser(description="同步当天会议到归档文件")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="拉取日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--output", choices=["human", "json"], default="human")
    args = parser.parse_args()

    keep_days = getattr(cfg, "MEETING_ARCHIVE_DAYS", 3)
    date_str  = args.date

    print(f"📅 同步会议记录：{date_str}")

    # 1. 加载本地 archive
    archive = load_archive()

    # 2. 清理过期记录
    purge_old(archive, keep_days)

    # 3. 拉取当天会议
    meetings = fetch_meetings(date_str)
    print(f"  📡 拉取到 {len(meetings)} 条会议")

    # 4. 新增未见过的会议 → pending
    new_count = 0
    for m in meetings:
        if m["id"] not in archive["meetings"]:
            archive["meetings"][m["id"]] = {
                "title":    m["title"],
                "date":     date_str,
                "start":    m["start"],
                "duration": m["duration"],
                "status":   "pending",
                "req_name": None
            }
            new_count += 1

    archive["last_sync"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    save_archive(archive)

    if new_count == 0:
        print("  ✅ 无新增会议，归档已是最新")
        return

    # 5. 列出所有 pending 条目，分批输出
    pending = [(mid, m) for mid, m in archive["meetings"].items() if m["status"] == "pending"]

    if args.output == "json":
        print(json.dumps({"pending": [{"id": mid, **m} for mid, m in pending]}, ensure_ascii=False))
        return

    total   = len(pending)
    batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\n📋 发现 {total} 条未归档会议，分 {batches} 批确认\n")

    for batch_i in range(batches):
        chunk = pending[batch_i * BATCH_SIZE : (batch_i + 1) * BATCH_SIZE]
        print(f"── 第 {batch_i+1} 批（{batch_i+1}/{batches}）──")
        for local_i, (mid, m) in enumerate(chunk, 1):
            start_fmt = m.get("start", "")[:16].replace("T", " ") if m.get("start") else "--:--"
            dur_str   = f"（{m['duration']}分钟）" if m.get("duration") else ""
            print(f"  {local_i}. [{start_fmt}] {m['title']}{dur_str}")
            print(f"     ID: {mid}")
        print()
        print("  回复格式：1-需求名称 2-忽略 3-需求名称 ...")
        print("  （确认完此批后继续下一批）")
        if batch_i < batches - 1:
            print()

if __name__ == "__main__":
    main()
