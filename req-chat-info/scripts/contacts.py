#!/usr/bin/env python3
"""
contacts.py — 本地联系人档案管理
联系人 JSON 存储在 req-chat-info/references/contacts.json

结构（以 WPS user_id 为主键，姓名作为可读标识）：
{
  "user_id_xxx": {
    "name": "孔尧",
    "role": "依赖方研发",
    "team": "AICP后端",
    "note": ""
  }
}

查询时优先按 user_id 匹配，fallback 按 name 模糊匹配（兼容旧数据和手动录入）。
"""
import json
import os

CONTACTS_FILE = os.path.join(os.path.dirname(__file__), "../references/contacts.json")

def load():
    if os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save(contacts):
    os.makedirs(os.path.dirname(CONTACTS_FILE), exist_ok=True)
    with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(contacts, f, ensure_ascii=False, indent=2)

def get_role(user_id=None, name=None):
    """
    查询角色。优先按 user_id，fallback 按 name。
    返回 role 字符串，或 None（未知）。
    """
    contacts = load()
    # 优先 user_id 精确匹配
    if user_id and user_id in contacts:
        return contacts[user_id]["role"]
    # fallback：按 name 匹配（兼容旧数据 / 手动录入场景）
    if name:
        for entry in contacts.values():
            if entry.get("name") == name:
                return entry["role"]
    return None

def upsert(user_id, name, role, team="", note=""):
    """新增或更新联系人（以 user_id 为主键）"""
    contacts = load()
    contacts[user_id] = {
        "name": name,
        "role": role,
        "team": team,
        "note": note,
    }
    save(contacts)
    return contacts[user_id]

def list_all():
    return load()
