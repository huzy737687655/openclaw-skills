#!/usr/bin/env python3
"""
req_chat_extract.py — 从需求沟通群中提取需求信息
用法：
  python3 req_chat_extract.py --group-name "【支持物理队列 AICP-2652】需求沟通群"
  python3 req_chat_extract.py --group-name "物理队列" --days 7
输出：结构化的需求信息（需求名称、产品经理、PRD、Ezone卡片等），
      可直接作为 req_add.py 的参数使用。
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

MCPORTER_CONFIG = os.path.join(os.path.dirname(__file__), "../../../wps-cli/mcporter.json")

# Ezone URL 模板
EZONE_URL_TPL = "https://ezone.ksyun.com/project/{project}/{seq}"

# 身份判断关键词（用于推断群成员角色）
ROLE_HINTS = {
    "产品经理": ["PRD", "prd", "需求", "产品", "设计稿", "Figma", "figma", "评审", "OpenAPI定义"],
    "前端":     ["设计文档", "figma", "Figma", "交互", "页面", "UI"],
    "研发":     ["API", "接口", "实现方案", "代码", "联调", "服务"],
    "测试":     ["测试", "用例", "QA", "提测"],
}

def mcpcall(tool, **kwargs):
    args_str = ", ".join(f"{k}: {json.dumps(v)}" for k, v in kwargs.items())
    cmd = ["mcporter", "--config", MCPORTER_CONFIG, "call", f"{tool}({args_str})"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"ERROR: {r.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(r.stdout.strip())

def search_group(keyword):
    """通过关键词搜索群聊，返回匹配的 chat 列表"""
    r = mcpcall("ksc-mcp-wps.mcp_message.search_chats",
        body={"page_size": 10, "keyword": keyword, "filter_chat_type_list": ["group"]})
    try:
        data = json.loads(r["result"]["content"][0]["text"])
        return data.get("items", [])
    except Exception:
        return []

def get_chat_messages(chat_id, days=7):
    """拉取群聊近 N 天的消息"""
    tz8 = timezone(timedelta(hours=8))
    now = datetime.now(tz8)
    start_ts = int((now - timedelta(days=days)).timestamp())

    r = mcpcall("ksc-mcp-wps.mcp_message.get_chat_messages",
        body={"chat_id": chat_id, "page_size": 50})
    try:
        items = json.loads(r["result"]["content"][0]["text"]).get("items", [])
    except Exception:
        items = []

    # 过滤时间范围（ctime 单位毫秒）
    return [m for m in items if m.get("ctime", 0) / 1000 >= start_ts]

def extract_docs_from_messages(messages):
    """从消息列表中提取文档链接、发送者、文本内容"""
    extracted = []
    for msg in messages:
        sender = msg.get("sender", {})
        sender_name = sender.get("name", "未知")
        ctime_ms = msg.get("ctime", 0)
        date_str = datetime.fromtimestamp(ctime_ms / 1000,
                   tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

        # 提取纯文本
        text_parts = []
        doc_links = []  # {type, name, url} from rich_text doc elements

        msg_type = msg.get("type", "")

        if msg_type == "text":
            text_parts.append(msg.get("content", {}).get("text", {}).get("content", ""))

        elif msg_type == "rich_text":
            elements = msg.get("content", {}).get("rich_text", {}).get("elements", [])
            for line in elements:
                for el in line.get("elements", []):
                    if el.get("type") == "text":
                        text_parts.append(el.get("text_content", {}).get("content", ""))
                    elif el.get("type") == "doc":
                        doc_content = el.get("doc_content", {})
                        doc_links.append({
                            "name": doc_content.get("name", "云文档"),
                            "url":  doc_content.get("url", ""),
                            "type": "doc"
                        })

        full_text = " ".join(t for t in text_parts if t.strip())

        # 从文本中提取 URL（kdocs / figma / ezone）
        urls = re.findall(r'https?://[^\s\u4e00-\u9fff"\'<>]+', full_text)
        for url in urls:
            if "kdocs.cn" in url:
                doc_links.append({"name": "云文档链接", "url": url, "type": "kdoc"})
            elif "figma.com" in url:
                doc_links.append({"name": "Figma设计稿", "url": url, "type": "figma"})
            elif "ezone.ksyun.com" in url:
                doc_links.append({"name": "Ezone卡片", "url": url, "type": "ezone"})

        if full_text.strip() or doc_links:
            extracted.append({
                "sender": sender_name,
                "sender_id": sender.get("id", ""),
                "date": date_str,
                "text": full_text.strip(),
                "docs": doc_links,
            })

    return extracted

def infer_role(sender_name, messages_by_sender):
    """根据发消息内容推断角色"""
    texts = " ".join(m["text"] for m in messages_by_sender.get(sender_name, []))
    for role, keywords in ROLE_HINTS.items():
        if any(kw in texts for kw in keywords):
            return role
    return "参与者"

def extract_ezone_from_group_name(group_name):
    """从群名中提取 AICP-XXXX 等 Ezone 卡片标识"""
    pattern = r'([A-Z]+)-(\d+)'
    m = re.search(pattern, group_name, re.IGNORECASE)
    if m:
        project = m.group(1).upper()
        seq = m.group(2)
        return {
            "project": project,
            "seq": seq,
            "url": EZONE_URL_TPL.format(project=project, seq=seq)
        }
    return None

def find_prd_doc(extracted_messages, req_name):
    """在提取的消息中找 PRD 文档（优先搜索云文档）"""
    # 先找消息里的 doc 链接，过滤带 PRD 关键词的
    for msg in extracted_messages:
        for doc in msg.get("docs", []):
            if doc["type"] in ("doc", "kdoc") and "PRD" in doc.get("name", ""):
                return doc

    # 没有的话搜云文档
    try:
        r = mcpcall("ksc-mcp-wps.mcp_yundoc.search",
            body={"keyword": f"PRD {req_name}", "page_size": 5})
        items = json.loads(r["result"]["content"][0]["text"]).get("items", [])
        for item in items:
            f = item.get("file", {})
            name = f.get("name", "")
            if "PRD" in name and (req_name.split()[0] in name or "物理队列" in name):
                return {"name": name, "url": f.get("link_url", ""), "type": "kdoc"}
    except Exception:
        pass
    return None

def main():
    parser = argparse.ArgumentParser(description="从需求沟通群提取需求信息")
    parser.add_argument("--group-name", required=True, help="群名关键词，如「物理队列 AICP-2652」")
    parser.add_argument("--days", type=int, default=7, help="拉取最近几天的消息（默认7天）")
    parser.add_argument("--output", choices=["human", "json"], default="human")
    args = parser.parse_args()

    group_keyword = args.group_name
    print(f"🔍 搜索群：{group_keyword}")

    # Step 1: 搜索群
    groups = search_group(group_keyword)
    if not groups:
        print(f"❌ 未找到包含「{group_keyword}」的群聊", file=sys.stderr)
        sys.exit(1)
    if len(groups) > 1:
        print(f"⚠️  找到 {len(groups)} 个匹配的群，使用第一个：")
        for g in groups:
            print(f"   - [{g['chat']['id']}] {g['chat']['name']}")
        print()

    chat = groups[0]["chat"]
    chat_id   = chat["id"]
    chat_name = chat["name"]
    print(f"  ✅ 群ID: {chat_id}  群名: {chat_name}")

    # Step 2: 从群名提取 Ezone 信息
    ezone_info = extract_ezone_from_group_name(chat_name)
    if ezone_info:
        print(f"  🔗 Ezone 卡片: {ezone_info['url']}")

    # Step 3: 拉取近 N 天消息
    print(f"\n📨 拉取近 {args.days} 天消息...")
    messages = get_chat_messages(chat_id, days=args.days)
    print(f"  共 {len(messages)} 条")

    # Step 4: 提取文档和文本
    extracted = extract_docs_from_messages(messages)

    # Step 5: 按发送者聚合，推断角色
    messages_by_sender = {}
    for m in extracted:
        messages_by_sender.setdefault(m["sender"], []).append(m)

    roles = {name: infer_role(name, messages_by_sender) for name in messages_by_sender}
    pm_candidates = [name for name, role in roles.items() if role == "产品经理"]

    # Step 6: 推断需求名（去掉群名里的括号标记）
    req_name = re.sub(r'[【】\[\]]', '', chat_name)
    req_name = re.sub(r'(需求沟通群|沟通群|讨论群).*', '', req_name).strip()
    if ezone_info:
        req_name = re.sub(rf'{ezone_info["project"]}-{ezone_info["seq"]}', '', req_name, flags=re.IGNORECASE).strip()
    req_name = req_name.strip('- ').strip()

    # Step 7: 找 PRD 文档
    prd = find_prd_doc(extracted, req_name)

    # Step 8: 收集所有文档
    all_docs = []
    seen_urls = set()
    for m in extracted:
        for doc in m.get("docs", []):
            url = doc.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_docs.append({**doc, "sender": m["sender"], "date": m["date"]})

    # 输出结果
    result = {
        "chat_id":   chat_id,
        "chat_name": chat_name,
        "req_name":  req_name,
        "ezone":     ezone_info["url"] if ezone_info else None,
        "prd":       prd["url"] if prd else None,
        "prd_name":  prd["name"] if prd else None,
        "pm":        pm_candidates[0] if pm_candidates else None,
        "participants": [
            {"name": name, "role": role}
            for name, role in sorted(roles.items(), key=lambda x: x[1])
        ],
        "docs": all_docs,
        "raw_message_count": len(messages),
    }

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 人类可读输出
    print(f"\n{'='*50}")
    print(f"📋 需求信息提取结果")
    print(f"{'='*50}")
    print(f"需求名称:  {result['req_name']}")
    print(f"Ezone卡片: {result['ezone'] or '未找到'}")
    print(f"PRD文档:   {result['prd'] or '未找到'}")
    if result['prd_name']:
        print(f"  ({result['prd_name']})")
    print(f"产品经理:  {result['pm'] or '未识别（需手动确认）'}")
    print()
    print("参与人员:")
    for p in result["participants"]:
        print(f"  - {p['name']} ({p['role']})")
    if result["docs"]:
        print()
        print("群内文档:")
        for doc in result["docs"]:
            print(f"  [{doc['type']}] {doc['name']}")
            print(f"    {doc['url']}")
            print(f"    发送人: {doc['sender']} @ {doc['date']}")
    print()
    print("─── 可直接用于 req_add.py 的参数 ───")
    cmd_parts = [f'python3 skills/req-tracker/scripts/req_add.py \\']
    cmd_parts.append(f'  --name "{result["req_name"]}" \\')
    if result["ezone"]:
        cmd_parts.append(f'  --ezone "{result["ezone"]}" \\')
    if result["prd"]:
        cmd_parts.append(f'  --prd "{result["prd"]}" \\')
    if result["pm"]:
        cmd_parts.append(f'  --pm "{result["pm"]}" \\')
    cmd_parts.append(f'  --status "待评估"')
    print("\n".join(cmd_parts))

if __name__ == "__main__":
    main()
