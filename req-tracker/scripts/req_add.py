#!/usr/bin/env python3
"""
req_add.py — 新增需求
自动创建：总览记录 + 详情记录 + 需求日志文档（季度文件夹下）
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
QUARTERS_FILE   = os.path.join(os.path.dirname(__file__), "../references/quarters.json")

def load_quarters():
    if os.path.exists(QUARTERS_FILE):
        with open(QUARTERS_FILE) as f:
            return json.load(f)
    return dict(cfg.QUARTER_FOLDERS)

def save_quarters(q):
    os.makedirs(os.path.dirname(QUARTERS_FILE), exist_ok=True)
    with open(QUARTERS_FILE, "w") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)

def quarter_key(date_str):
    month = int(date_str[5:7])
    q = (month - 1) // 3 + 1
    return f"{date_str[:4]}-Q{q}"

def mcpcall(tool, **kwargs):
    args = ", ".join(f"{k}: {json.dumps(v)}" for k, v in kwargs.items())
    cmd = ["mcporter", "--config", MCPORTER_CONFIG, "call", f"{tool}({args})"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"ERROR calling {tool}: {r.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(r.stdout.strip())

def get_or_create_quarter_folder(date_str):
    quarters = load_quarters()
    key = quarter_key(date_str)
    if key in quarters:
        return quarters[key]
    r = mcpcall("ksc-mcp-wps.file.create_in_folder",
        path_params={"drive_id": cfg.DRIVE_ID, "parent_id": cfg.LOG_ROOT_ID},
        body={"name": key, "file_type": "folder", "on_name_conflict": "fail"})
    if r.get("code") == 0:
        folder_id = r["data"]["id"]
    else:
        print(f"创建季度文件夹失败: {r}", file=sys.stderr)
        sys.exit(1)
    quarters[key] = folder_id
    save_quarters(quarters)
    return folder_id

def main():
    parser = argparse.ArgumentParser(description="新增需求到管理台账")
    parser.add_argument("--name",     required=True,  help="需求名称")
    parser.add_argument("--ezone",    default="",     help="Ezone 卡片链接")
    parser.add_argument("--prd",      default="",     help="PRD 文档链接")
    parser.add_argument("--pm",       default="",     help="产品经理")
    parser.add_argument("--dev",      default="",     help="依赖方研发")
    parser.add_argument("--frontend", default="",     help="前端同学")
    parser.add_argument("--projects", default="",     help="涉及项目")
    parser.add_argument("--config",   default="",     help="涉及配置")
    parser.add_argument("--dep-doc",  default="",     help="依赖层文档链接（保留兼容）")
    parser.add_argument("--docs",     default="",     help='文档汇总 JSON，写入日志文档关联资源章节，格式：[{"type":"PRD","name":"xxx","url":"yyy","sender":"zzz"}]')
    parser.add_argument("--ui",       default="",     help="UI同学")
    parser.add_argument("--status",   default="待评估", help="初始状态")
    parser.add_argument("--date",     default=datetime.now().strftime("%Y-%m-%d"), help="需求提出时间 YYYY-MM-DD")
    args = parser.parse_args()

    name = args.name
    date = args.date
    print(f"📋 新增需求: {name}")

    # Step 1: 创建详情记录
    detail_fields = {"需求名称": name}
    if args.pm:       detail_fields["产品经理"] = args.pm
    if args.dev:      detail_fields["依赖方研发"] = args.dev
    if args.frontend: detail_fields["前端同学"] = args.frontend
    if args.projects: detail_fields["涉及项目"] = args.projects
    if args.config:   detail_fields["涉及配置"] = args.config
    if args.dep_doc:  detail_fields["依赖层文档"] = args.dep_doc
    r_detail = mcpcall("wps365.dbsheet.create_records",
        path_params={"file_id": cfg.DB_FILE_ID, "sheet_id": cfg.SHEET_DETAIL},
        body={"records": [{"fields_value": json.dumps(detail_fields, ensure_ascii=False)}]})
    if r_detail.get("code") != 0:
        print(f"❌ 创建详情记录失败: {r_detail}", file=sys.stderr)
        sys.exit(1)
    detail_record_id = r_detail["data"]["records"][0]["id"]
    print(f"  ✅ 详情记录 ID: {detail_record_id}")

    # Step 2: 创建需求日志文档
    quarter_folder_id = get_or_create_quarter_folder(date)
    month_day = date[5:]  # MM-DD
    doc_name = f"{month_day}-[{name}]"

    # 构建关联资源章节
    docs_list = []
    if args.docs:
        try:
            docs_list = json.loads(args.docs)
        except Exception:
            pass

    # 按类型分组
    DOC_SECTIONS = [
        ("prd",   "📄 PRD 文档"),
        ("ui",    "🎨 UI 设计稿"),
        ("api",   "🔌 API / 接口文档"),
        ("impl",  "🏗 实现方案"),
        ("ezone", "📌 Ezone 卡片"),
        ("other", "📎 其他文档"),
    ]
    doc_section_lines = []
    docs_by_type = {}
    for doc in docs_list:
        docs_by_type.setdefault(doc.get("type_key", "other"), []).append(doc)

    # 加载联系人档案，用于查 role/team
    contacts_file = os.path.join(os.path.dirname(__file__),
                                 "../../req-chat-info/references/contacts.json")
    contacts = {}
    if os.path.exists(contacts_file):
        with open(contacts_file, encoding="utf-8") as f:
            contacts = json.load(f)

    def sender_label(sender_name):
        """返回 '依赖方研发/KAIC后端 - 孔尧' 格式，找不到就直接返回姓名"""
        for entry in contacts.values():
            if entry.get("name") == sender_name:
                role = entry.get("role", "")
                team = entry.get("team", "")
                label = "/".join(filter(None, [role, team]))
                return f"{label} - {sender_name}" if label else sender_name
        return sender_name

    for type_key, section_title in DOC_SECTIONS:
        docs = docs_by_type.get(type_key, [])
        if not docs:
            continue
        doc_section_lines.append(f"\n### {section_title}")
        for doc in docs:
            sender = doc.get("sender", "")
            date_str = doc.get("date", "")
            if sender and sender != "云文档搜索":
                sender_str = f"（{sender_label(sender)}）"
            elif sender == "云文档搜索":
                sender_str = "（云文档搜索）"
            else:
                sender_str = ""
            doc_section_lines.append(
                f"- [{doc.get('name','文档')}]({doc.get('url','')}) {sender_str}"
            )

    # Ezone / PRD 单独补充（来自参数，防止 --docs 为空时遗漏）
    if args.ezone and "ezone" not in docs_by_type:
        doc_section_lines.append(f"\n### 📌 Ezone 卡片\n- [EZONE 卡片]({args.ezone})")
    if args.prd and "prd" not in docs_by_type:
        doc_section_lines.append(f"\n### 📄 PRD 文档\n- [PRD 文档]({args.prd})")

    resource_block = "\n".join(doc_section_lines) if doc_section_lines else "（暂无，待补充）"

    log_template = f"""# {doc_name} 需求日志

## 基本信息
- **需求名称**: {name}
- **产品经理**: {args.pm or '待确认'}
- **UI同学**: {args.ui or '待确认'}
- **前端同学**: {args.frontend or '待确认'}
- **依赖方研发**: {args.dev or '待确认'}
- **创建时间**: {date}

---

## 关联资源
{resource_block}

### 需求相关群
| 群名称 | 群ID | 备注 |
|--------|------|------|
| 待补充 | | |

### 会议记录
| 会议主题 | 会议ID | 日期 | 关键结论 |
|----------|--------|------|----------|
| 待补充 | | | |

---

## 进展日志

### {date}
- 需求日志文档初始化创建

---

## 决策记录

---

## 待办事项
"""
    r_doc = mcpcall("wps-dailyoffice.write_doc",
        action="create",
        name=doc_name,
        doc_type="doc",
        content_markdown=log_template,
        target_folder_id=quarter_folder_id)
    if not r_doc.get("file"):
        print(f"❌ 创建日志文档失败: {r_doc}", file=sys.stderr)
        sys.exit(1)
    doc_url = r_doc["file"]["link_url"]
    print(f"  ✅ 日志文档: {doc_url}")

    # Step 3: 把日志文档 URL 写回详情记录
    r_upd = mcpcall("wps365.dbsheet.update_records",
        path_params={"file_id": cfg.DB_FILE_ID, "sheet_id": cfg.SHEET_DETAIL},
        body={"records": [{"id": detail_record_id,
                           "fields_value": json.dumps({"需求日志文档": doc_url}, ensure_ascii=False)}]})
    if r_upd.get("code") != 0:
        print(f"⚠️  更新详情记录日志URL失败: {r_upd}", file=sys.stderr)

    # Step 4: 创建总览记录
    overview_fields = {
        "需求名称": name,
        "当前状态": args.status,
        "详情记录ID": detail_record_id,
    }
    if args.ezone: overview_fields["Ezone卡片"] = args.ezone
    if args.prd:   overview_fields["PRD文档"]   = args.prd
    if date:       overview_fields["需求提出时间"] = date

    r_ov = mcpcall("wps365.dbsheet.create_records",
        path_params={"file_id": cfg.DB_FILE_ID, "sheet_id": cfg.SHEET_OVERVIEW},
        body={"records": [{"fields_value": json.dumps(overview_fields, ensure_ascii=False)}]})
    if r_ov.get("code") != 0:
        print(f"❌ 创建总览记录失败: {r_ov}", file=sys.stderr)
        sys.exit(1)
    ov_id = r_ov["data"]["records"][0]["id"]
    print(f"  ✅ 总览记录 ID: {ov_id}")

    print(f"\n🎉 需求【{name}】添加完成")
    if cfg.DB_URL:
        print(f"   台账: {cfg.DB_URL}")
    print(f"   日志: {doc_url}")

if __name__ == "__main__":
    main()
