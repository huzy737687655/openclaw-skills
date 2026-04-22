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
    """拉取指定日期的会议列表，返回 [{id, title, start, duration_min, creator, transcripts}]

    关键路径（已验证）：
    1. ksc-mcp-wps.mcp_meeting.list(body: {start_date_time: unix_sec, end_date_time: unix_sec})
       → 返回 items 列表，含 id/join_code/creator_name/booking/start_date_time/end_date_time
       - 即时会议的 booking.start_date_time=0，用 ctime_str 代替
       - 会议标题在 meeting_name 字段（通常为空），日历标题要另从 calendar 接口取
    2. wps365.meeting.get(path_params: {meeting_id: "3-xx-xxx"})
       → 返回 subject / transcripts 数组（含 transcript_id、title、state）
       - transcripts 是 AI 纪要/逐字稿的入口，未开录制则为空
    3. ksc-mcp-wps.mcp_meeting.get_transcript(body: {meeting_id, transcript_id})
       → 返回完整逐字稿 JSON：paragraphs[].{speaker.name, start_time(ms), sentenses[].text}
    """
    tz8 = timezone(timedelta(hours=8))
    day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz8)
    start_ts = int(day.timestamp())
    end_ts   = int((day + timedelta(days=1)).timestamp())

    r = mcpcall("ksc-mcp-wps.mcp_meeting.list",
        body={"start_date_time": start_ts, "end_date_time": end_ts, "page_size": 50})

    try:
        content = r["result"]["content"][0]["text"]
        data = json.loads(content)
        items = data.get("items") or data.get("meetings") or []
    except Exception:
        items = []

    result = []
    for m in items:
        mid      = m.get("id", "")
        # 即时会议 meeting_name 通常为 None，subject 需要调 wps365.meeting.get 才有
        title    = m.get("meeting_name") or ""
        creator  = m.get("creator_name", "")
        # 时间：有预约用 booking，即时会议 booking.start=0 则用 ctime
        bk       = m.get("booking", {})
        if bk.get("start_date_time"):
            start_str = bk.get("start_date_time_str", "")
            end_str   = bk.get("end_date_time_str", "")
        else:
            start_str = m.get("ctime_str", "")
            end_str   = m.get("end_date_time_str", "")
        # 时长（分钟）
        dur = 0
        if start_str and end_str:
            try:
                fmt = "%Y-%m-%d %H:%M:%S"
                dur = int((datetime.strptime(end_str, fmt) -
                           datetime.strptime(start_str, fmt)).total_seconds() / 60)
            except Exception:
                pass
        if mid:
            result.append({
                "id":          mid,
                "title":       title,
                "creator":     creator,
                "start":       start_str,
                "end":         end_str,
                "duration":    dur,
                "transcripts": [],   # 后续按需调 get_meeting_transcripts() 填充
            })
    return result


def get_meeting_transcripts(meeting_id):
    """获取会议的逐字稿列表（通过 wps365.meeting.get 的 transcripts 字段）

    返回 [{"transcript_id": str, "title": str, "state": str}]
    state="success" 表示已生成完毕
    """
    r = mcpcall("wps365.meeting.get", path_params={"meeting_id": meeting_id})
    try:
        text = r["result"]["content"][0]["text"]
        data = json.loads(text)
        # 兼容 {code:0, data:{...}} 和直接返回对象两种格式
        obj = data.get("data", data)
        raw = obj.get("transcripts") or []
        return [
            {"transcript_id": t.get("id", ""), "title": t.get("title", ""), "state": t.get("state", "")}
            for t in raw if t.get("id")
        ]
    except Exception:
        return []


def get_transcript_text(meeting_id, transcript_id):
    """拉取完整逐字稿，返回格式化文本（每行 [MM:SS] 发言人: 内容）"""
    r = mcpcall("ksc-mcp-wps.mcp_meeting.get_transcript",
                body={"meeting_id": meeting_id, "transcript_id": transcript_id})
    try:
        text = r["result"]["content"][0]["text"]
        data = json.loads(text)
        paras = data.get("paragraphs", [])
    except Exception:
        return ""

    lines = []
    for p in paras:
        speaker = p.get("speaker", {}).get("name", "?").split("#")[0]
        content = "".join(s.get("text", "") for s in p.get("sentenses", []))
        ms = p.get("start_time", 0)
        m, s = divmod(ms // 1000, 60)
        if content.strip():
            lines.append(f"[{m:02d}:{s:02d}] {speaker}: {content}")
    return "\n".join(lines)

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

    # 4. 新增未见过的会议 → pending（顺带拉 transcripts 信息）
    new_count = 0
    for m in meetings:
        if m["id"] not in archive["meetings"]:
            # 拉 subject 和 transcripts（wps365.meeting.get）
            transcripts = get_meeting_transcripts(m["id"])
            # subject：wps365 返回的 subject 字段（如「胡志勇 - 唐静鑫」），transcript title 更有意义
            subject = m["title"] or (transcripts[0]["title"] if transcripts else "（无主题）")
            archive["meetings"][m["id"]] = {
                "title":       subject,
                "creator":     m.get("creator", ""),
                "date":        date_str,
                "start":       m["start"],
                "duration":    m["duration"],
                "status":      "pending",
                "req_name":    None,
                "transcripts": transcripts,   # [{transcript_id, title, state}]
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
            start_fmt = m.get("start", "")[:16] if m.get("start") else "--:--"
            dur_str   = f"（{m['duration']}分钟）" if m.get("duration") else ""
            creator   = f" by {m['creator']}" if m.get("creator") else ""
            print(f"  {local_i}. [{start_fmt}]{creator} {m['title']}{dur_str}")
            print(f"     ID: {mid}")
            # 展示 transcript 信息（有逐字稿则提示）
            transcripts = m.get("transcripts", [])
            ok = [t for t in transcripts if t.get("state") == "success"]
            if ok:
                print(f"     📝 有AI纪要: {ok[0]['title']}")
            elif transcripts:
                print(f"     ⏳ 纪要处理中")
            else:
                print(f"     —  无AI纪要")
        print()
        print("  回复格式：1-需求名称 2-忽略 3-需求名称 ...")
        print("  （确认完此批后继续下一批）")
        if batch_i < batches - 1:
            print()

if __name__ == "__main__":
    main()
