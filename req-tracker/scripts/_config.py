"""
从 req-tracker/config.json 加载配置
config.json 不提交到 git，请复制 config.example.json 并填入真实值
"""
import json
import os
import sys

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config.json")

def load():
    if not os.path.exists(_CONFIG_PATH):
        print(f"❌ 找不到配置文件: {_CONFIG_PATH}", file=sys.stderr)
        print("   请复制 config.example.json 为 config.json 并填入真实值", file=sys.stderr)
        sys.exit(1)
    with open(_CONFIG_PATH) as f:
        return json.load(f)

_cfg = load()

DRIVE_ID        = _cfg["DRIVE_ID"]
DB_FILE_ID      = _cfg["DB_FILE_ID"]
DB_URL          = _cfg.get("DB_URL", "")
SHEET_OVERVIEW  = _cfg.get("SHEET_OVERVIEW", 10)
SHEET_DETAIL    = _cfg.get("SHEET_DETAIL", 12)
LOG_ROOT_ID     = _cfg["LOG_ROOT_ID"]
QUARTER_FOLDERS = _cfg.get("QUARTER_FOLDERS", {})
