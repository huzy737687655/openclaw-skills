#!/usr/bin/env python3
"""
extract.py — 从需求沟通群中提取结构化需求信息
用法：
  python3 extract.py --group-name "支持物理队列 AICP-2652" [--days 7] [--output human|json]
  python3 extract.py --confirm-roles '{"孔尧":"依赖方研发","徐彤昊":"前端"}'
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import contacts as contacts_db

MCPORTER_CONFIG = os.path.join(os.path.dirname(__file__), "../../wps-cli/mcporter.json")
EZONE_URL_TPL   = "https://ezone.ksyun.com/project/{project}/{seq}"

# ── 人员角色推断关键词 ────────────────────────────────────────────────────────
# UI同学发 Figma/设计稿；前端发联调/页面问题；研发发接口/实现方案
ROLE_HINTS = {
    "产品经理": ["PRD", "prd", "需求文档", "评审", "OpenAPI定义", "需求说明", "验收标准"],
    "UI":       ["figma", "Figma", "设计稿", "设计文档", "交互设计", "UI稿", "视觉"],
    "前端":     ["前端", "联调", "页面问题", "样式", "组件", "webpack", "vue", "react"],
    "研发":     ["API文档", "接口文档", "实现方案", "设计方案", "后端", "服务端", "OpenAPI", "swagger"],
    "测试":     ["测试用例", "QA", "提测", "测试报告", "冒烟"],
}

# ── 文档类型识别规则 ─────────────────────────────────────────────────────────
DOC_RULES = [
    (1, "prd",   "PRD文档",    ["PRD", "prd", "需求文档"],                                         ["kdocs.cn"]),
    (2, "ui",    "UI设计稿",   ["设计稿", "设计文档", "UI稿", "交互设计", "视觉"],                  ["figma.com", "mastergo.com"]),
    (3, "api",   "依赖层文档", ["API文档", "接口文档", "OpenAPI", "swagger", "API变化", "API 变化",
                                "接口变更", "接口变化", "API变更"],                                 ["kdocs.cn", "365.kdocs.cn", "apifox", "swagger"]),
    (4, "impl",  "依赖层文档", ["实现方案", "控制台实现", "后端方案", "设计方案", "任务文档"],       ["kdocs.cn", "365.kdocs.cn"]),
    (5, "ezone", "Ezone卡片",  ["ezone"],                                                          ["ezone.ksyun.com"]),
]

def classify_doc(name, url):
    """
    按规则分类文档，返回 (type_key, field_name)。
    无法归类时返回 ("unknown", None)，调用方需要向用户询问。
    """
    name_lower = (name or "").lower()
    url_lower  = (url  or "").lower()
    for _, type_key, field_name, name_kws, url_kws in sorted(DOC_RULES, key=lambda x: x[0]):
        name_hit = any(kw.lower() in name_lower for kw in name_kws)
        url_hit  = any(kw.lower() in url_lower  for kw in url_kws)
        if name_hit or (url_hit and name_kws == []):
            return type_key, field_name
    return "unknown", None  # 需要人工确认

def mcpcall(tool, **kwargs):
    args_str = ", ".join(f"{k}: {json.dumps(v)}" for k, v in kwargs.items())
    cmd = ["mcporter", "--config", MCPORTER_CONFIG, "call", f"{tool}({args_str})"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"ERROR: {r.stderr}", file=sys.stderr); sys.exit(1)
    return json.loads(r.stdout.strip())

def search_group(keyword):
    r = mcpcall("ksc-mcp-wps.mcp_message.search_chats",
        body={"page_size": 10, "keyword": keyword, "filter_chat_type_list": ["group"]})
    try:
        return json.loads(r["result"]["content"][0]["text"]).get("items", [])
    except Exception:
        return []

def get_chat_messages(chat_id, days=7):
    tz8 = timezone(timedelta(hours=8))
    start_ts = int((datetime.now(tz8) - timedelta(days=days)).timestamp())
    r = mcpcall("ksc-mcp-wps.mcp_message.get_chat_messages",
        body={"chat_id": chat_id, "page_size": 50})
    try:
        items = json.loads(r["result"]["content"][0]["text"]).get("items", [])
    except Exception:
        items = []
    return [m for m in items if m.get("ctime", 0) / 1000 >= start_ts]

def parse_messages(messages):
    extracted = []
    for msg in messages:
        sender      = msg.get("sender", {})
        sender_name = sender.get("name", "未知")
        date_str    = datetime.fromtimestamp(
            msg.get("ctime", 0) / 1000,
            tz=timezone(timedelta(hours=8))
        ).strftime("%Y-%m-%d %H:%M")

        text_parts, docs = [], []
        msg_type = msg.get("type", "")

        if msg_type == "text":
            text_parts.append(msg.get("content", {}).get("text", {}).get("content", ""))
        elif msg_type == "rich_text":
            for line in msg.get("content", {}).get("rich_text", {}).get("elements", []):
                for el in line.get("elements", []):
                    if el.get("type") == "text":
                        text_parts.append(el.get("text_content", {}).get("content", ""))
                    elif el.get("type") == "doc":
                        dc = el.get("doc_content", {})
                        docs.append({"name": dc.get("name", "云文档"), "url": dc.get("url", ""), "source": "inline"})

        full_text = " ".join(t for t in text_parts if t.strip())
        for url in re.findall(r'https?://[^\s\u4e00-\u9fff"\'<>]+', full_text):
            label = "Figma设计稿" if "figma.com" in url else \
                    "Ezone卡片"   if "ezone.ksyun.com" in url else "云文档链接"
            docs.append({"name": label, "url": url, "source": "text"})

        if full_text.strip() or docs:
            extracted.append({
                "sender":    sender_name,
                "sender_id": sender.get("id", ""),
                "date":      date_str,
                "text":      full_text.strip(),
                "docs":      docs,
            })
    return extracted

def infer_roles(extracted):
    """
    角色推断优先级：
    1. 本地联系人档案（contacts.json）
    2. 发言内容关键词匹配
    3. 发出过文档但无法判断 → 标记为 "未知（发过文档）"
    4. 其他 → "参与者"
    """
    texts_by_sender  = {}
    has_docs_by_sender = {}
    for m in extracted:
        texts_by_sender.setdefault(m["sender"], []).append(m["text"])
        if m.get("docs"):
            has_docs_by_sender[m["sender"]] = True

    result = {}
    for sender in texts_by_sender:
        # 1. 查联系人档案
        known_role = contacts_db.get_role(sender)
        if known_role:
            result[sender] = known_role
            continue

        # 2. 关键词匹配（文本 + 文档名）
        combined = " ".join(texts_by_sender[sender])
        for m in extracted:
            if m["sender"] == sender:
                for doc in m.get("docs", []):
                    combined += " " + doc.get("name", "") + " " + doc.get("url", "")

        matched = None
        for role, kws in ROLE_HINTS.items():
            if any(kw in combined for kw in kws):
                matched = role
                break

        if matched:
            result[sender] = matched
        elif has_docs_by_sender.get(sender):
            # 3. 发过文档但识别不出角色 → 需要确认
            result[sender] = "未知（发过文档）"
        else:
            result[sender] = "参与者"

    return result

def search_prd_in_cloud(req_name):
    try:
        r = mcpcall("ksc-mcp-wps.mcp_yundoc.search",
            body={"keyword": f"PRD {req_name}", "page_size": 5})
        items = json.loads(r["result"]["content"][0]["text"]).get("items", [])
        for item in items:
            f = item.get("file", {})
            if "PRD" in f.get("name", ""):
                return {"name": f["name"], "url": f.get("link_url", ""), "source": "search"}
    except Exception:
        pass
    return None

def extract_ezone_from_name(group_name):
    m = re.search(r'([A-Z]+)-(\d+)', group_name, re.IGNORECASE)
    if m:
        project, seq = m.group(1).upper(), m.group(2)
        return {"project": project, "seq": seq,
                "url": EZONE_URL_TPL.format(project=project, seq=seq)}
    return None

def clean_req_name(chat_name, ezone_info):
    name = re.sub(r'[【】\[\]]', '', chat_name)
    name = re.sub(r'(需求沟通群|需求群|沟通群|讨论群).*', '', name)
    if ezone_info:
        name = re.sub(rf'{ezone_info["project"]}-{ezone_info["seq"]}',
                      '', name, flags=re.IGNORECASE)
    return name.strip('- ').strip()

def main():
    parser = argparse.ArgumentParser(description="从需求沟通群提取结构化需求信息")
    parser.add_argument("--group-name",    help="群名关键词")
    parser.add_argument("--days",          type=int, default=7)
    parser.add_argument("--output",        choices=["human", "json"], default="human")
    parser.add_argument("--confirm-roles", help='确认未知人员角色，JSON格式：{"姓名":"角色","姓名2":"角色2"}')
    parser.add_argument("--list-contacts", action="store_true", help="列出所有已知联系人")
    args = parser.parse_args()

    # ── 子命令：列出联系人 ────────────────────────────────────────────────────
    if args.list_contacts:
        contacts = contacts_db.list_all()
        if not contacts:
            print("（联系人档案为空）")
        else:
            print(f"{'姓名':<12} {'角色':<12} {'团队'}")
            print("─" * 40)
            for name, info in contacts.items():
                print(f"{name:<12} {info.get('role',''):<12} {info.get('team','')}")
        return

    # ── 子命令：确认未知人员角色并写入档案 ────────────────────────────────────
    if args.confirm_roles:
        try:
            confirmations = json.loads(args.confirm_roles)
        except Exception:
            print("--confirm-roles 格式错误，应为 JSON 字符串", file=sys.stderr)
            sys.exit(1)
        for name, role in confirmations.items():
            contacts_db.upsert(name, role)
            print(f"  ✅ 已保存: {name} → {role}")
        print(f"\n共保存 {len(confirmations)} 条联系人信息。")
        return

    if not args.group_name:
        parser.error("--group-name 或 --confirm-roles 或 --list-contacts 必须指定一个")

    # ── 主流程：提取群信息 ─────────────────────────────────────────────────────
    print(f"🔍 搜索群：{args.group_name}")
    groups = search_group(args.group_name)
    if not groups:
        print(f"❌ 未找到群：{args.group_name}", file=sys.stderr); sys.exit(1)
    if len(groups) > 1:
        print(f"⚠️  找到 {len(groups)} 个匹配群，使用第一个：")
        for g in groups:
            print(f"   [{g['chat']['id']}] {g['chat']['name']}")

    chat      = groups[0]["chat"]
    chat_id   = chat["id"]
    chat_name = chat["name"]
    print(f"  ✅ 群ID: {chat_id}  群名: {chat_name}")

    ezone_info = extract_ezone_from_name(chat_name)
    req_name   = clean_req_name(chat_name, ezone_info)

    print(f"\n📨 拉取近 {args.days} 天消息...")
    messages  = get_chat_messages(chat_id, days=args.days)
    extracted = parse_messages(messages)
    print(f"  共 {len(messages)} 条")

    # 聚合文档
    seen_urls, all_docs, unknown_docs = set(), [], []
    for m in extracted:
        for doc in m.get("docs", []):
            url = doc.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            type_key, field_name = classify_doc(doc["name"], url)
            entry = {**doc, "type_key": type_key, "field_name": field_name,
                     "sender": m["sender"], "date": m["date"]}
            if type_key == "unknown":
                unknown_docs.append(entry)
            else:
                all_docs.append(entry)

    prd_doc = next((d for d in all_docs if d["type_key"] == "prd"), None)
    if not prd_doc:
        fallback = search_prd_in_cloud(req_name)
        if fallback:
            type_key, field_name = classify_doc(fallback["name"], fallback["url"])
            prd_doc = {**fallback, "type_key": type_key, "field_name": field_name,
                       "sender": "云文档搜索", "date": ""}
            all_docs.insert(0, prd_doc)

    # 推断角色
    roles         = infer_roles(extracted)
    unknown_doc_senders = [n for n, r in roles.items() if r == "未知（发过文档）"]
    pm_list       = [n for n, r in roles.items() if r == "产品经理"]
    ui_list       = [n for n, r in roles.items() if r == "UI"]
    frontend_list = [n for n, r in roles.items() if r == "前端"]
    dev_list      = [n for n, r in roles.items() if r == "研发" or r == "依赖方研发"]

    docs_by_field = {}
    for doc in all_docs:
        docs_by_field.setdefault(doc["field_name"], []).append(doc)

    result = {
        "chat_id":   chat_id,
        "chat_name": chat_name,
        "req_name":  req_name,
        "ezone":     ezone_info["url"] if ezone_info else None,
        "prd":       prd_doc["url"] if prd_doc else None,
        "pm":        pm_list[0] if pm_list else None,
        "ui":        ", ".join(ui_list) or None,
        "frontend":  ", ".join(frontend_list) or None,
        "dev":       ", ".join(dev_list) or None,
        "participants":          [{"name": n, "role": r} for n, r in sorted(roles.items(), key=lambda x: x[1])],
        "unknown_doc_senders":   unknown_doc_senders,
        "unknown_docs":          unknown_docs,
        "docs_by_field":         docs_by_field,
        "all_docs":              all_docs,
    }

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # ── 人类可读输出 ──────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"📋 需求信息提取结果")
    print(f"{'='*55}")
    print(f"需求名称:   {result['req_name']}")
    print(f"Ezone卡片:  {result['ezone'] or '未找到'}")
    print(f"PRD文档:    {result['prd'] or '未找到'}")
    print()
    print(f"产品经理:   {result['pm']       or '未识别'}")
    print(f"UI同学:     {result['ui']        or '未识别'}")
    print(f"前端同学:   {result['frontend']  or '未识别'}")
    print(f"依赖方研发: {result['dev']       or '未识别'}")
    print()
    print("参与人员:")
    for p in result["participants"]:
        marker = " ⚠️" if p["role"] == "未知（发过文档）" else ""
        print(f"  - {p['name']} ({p['role']}){marker}")

    FIELD_ORDER = ["PRD文档", "UI设计稿", "依赖层文档", "Ezone卡片", "附件"]
    has_docs = False
    for field in FIELD_ORDER:
        docs = docs_by_field.get(field, [])
        if not docs:
            continue
        if not has_docs:
            print(f"\n群内文档（按类型分类）:")
            has_docs = True
        print(f"\n  【{field}】")
        for doc in docs:
            print(f"    · {doc['name']}")
            print(f"      {doc['url']}")
            if doc.get("sender"):
                print(f"      发送人: {doc['sender']}  {doc.get('date','')}")

    # ── 未知角色人员询问 ──────────────────────────────────────────────────────
    if unknown_doc_senders:
        print(f"\n{'─'*55}")
        print("⚠️  以下人员发过文档，但我不认识他们的身份，请告诉我：")
        for i, name in enumerate(unknown_doc_senders, 1):
            their_docs = [d for d in all_docs if d.get("sender") == name]
            doc_names  = "、".join(d["name"] for d in their_docs) or "（文档名未知）"
            print(f"  {i}. {name}  →  发过：{doc_names}")
        print()
        print("角色选项：产品经理 / UI / 前端 / 依赖方研发 / 测试 / 其他")
        confirm_example = json.dumps(
            {name: "角色" for name in unknown_doc_senders}, ensure_ascii=False)
        print(f"\n  --confirm-roles '{confirm_example}'")

    # ── 无法分类的文档询问 ───────────────────────────────────────────────────
    if unknown_docs:
        print(f"\n{'─'*55}")
        print("⚠️  以下文档我不确定是什么类型，请告诉我应该归到哪类：")
        type_options = "PRD文档 / UI设计稿 / 依赖层文档（API/实现方案）/ 附件 / 忽略"
        for i, doc in enumerate(unknown_docs, 1):
            print(f"  {i}. 【{doc['name']}】")
            print(f"     链接: {doc['url']}")
            print(f"     发送人: {doc.get('sender','')} @ {doc.get('date','')}")
        print(f"\n  类型选项：{type_options}")
        print("  告诉我后我会把它归入正确分类并写进日志文档。")

    print(f"\n{'─'*55}")
    print("可直接用于 req_add.py 的参数：")
    lines = ["python3 skills/req-tracker/scripts/req_add.py \\",
             f'  --name "{result["req_name"]}" \\']
    if result["ezone"]:   lines.append(f'  --ezone "{result["ezone"]}" \\')
    if result["prd"]:     lines.append(f'  --prd "{result["prd"]}" \\')
    if result["pm"]:      lines.append(f'  --pm "{result["pm"]}" \\')
    if result["ui"]:      lines.append(f'  --ui "{result["ui"]}" \\')
    if result["dev"]:     lines.append(f'  --dev "{result["dev"]}" \\')
    if result["frontend"]:lines.append(f'  --frontend "{result["frontend"]}" \\')
    if all_docs:
        docs_json = json.dumps(all_docs, ensure_ascii=False)
        lines.append(f"  --docs '{docs_json}' \\")
    lines.append(f'  --status "待评估"')
    print("\n".join(lines))

if __name__ == "__main__":
    main()
