#!/usr/bin/env python3
"""
contacts.py — 本地联系人档案管理
联系人 JSON 存储在 req-chat-info/references/contacts.json
格式：{ "姓名": { "role": "角色", "team": "所属团队", "note": "备注" }, ... }
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

def get_role(name):
    """查询联系人角色，不存在返回 None"""
    return load().get(name, {}).get("role")

def upsert(name, role, team="", note=""):
    """新增或更新联系人"""
    contacts = load()
    contacts[name] = {
        "role": role,
        "team": team,
        "note": note,
    }
    save(contacts)
    return contacts[name]

def list_all():
    return load()
