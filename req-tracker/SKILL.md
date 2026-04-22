---
name: req-tracker
description: 需求管理台账操作技能。用于在 WPS 多维表中管理研发需求全生命周期，包括：新增需求（自动创建总览记录+详情记录+需求日志文档）、更新需求状态或关键时间节点、查询需求列表或详情、从会议纪要/群聊自动追加日志到需求日志文档。当用户说"新增需求"、"更新需求状态"、"查看需求列表"、"把会议内容写进需求日志"、"需求提测了"、"需求上线了"等与需求跟踪相关的操作时触发。
---

# 需求管理台账 Skill

## 核心配置

```python
DRIVE_ID     = "LazE8wX"
DB_FILE_ID   = "4xGJbDenmxMrRgWLhxVY1x64KCEum7ZGC"   # 需求管理台账.dbt
DB_URL       = "https://www.kdocs.cn/l/cgjRzNidLF5P"
SHEET_OVERVIEW = 10   # 需求总览
SHEET_DETAIL   = 12   # 需求详情
LOG_ROOT_ID  = "j1mQ9XUCurMNDpMH1R7urxym6AbPT77gn"   # 需求日志文档/
MCPORTER_CONFIG = "/home/node/.openclaw/workspace/skills/wps-cli/mcporter.json"
```

季度文件夹 ID（按需扩充）：
```python
QUARTER_FOLDERS = {
    "2026-Q2": "n6CW5xmmo1M3iqwAYYee1xC86uShcAsLf",  # 2026-04 ~ 2026-06
}
```

> **获取当前季度文件夹 ID**：用 `get_quarter_folder_id()` 自动计算，若不存在则创建。

---

## 字段结构

**需求总览（Sheet 10）**
| 字段 | 类型 | 字段ID |
|------|------|--------|
| 需求名称 | MultiLineText | V |
| Ezone卡片 | Url | W |
| PRD文档 | Url | X |
| 需求提出时间 | Date | Y |
| 当前状态 | SingleSelect | Z |
| 详情记录ID | MultiLineText | 0 |

**需求详情（Sheet 12）**
| 字段 | 类型 | 字段ID |
|------|------|--------|
| 需求名称 | MultiLineText | BB |
| 产品经理 | MultiLineText | BC |
| 依赖方研发 | MultiLineText | BD |
| 前端同学 | MultiLineText | BE |
| 涉及项目 | MultiLineText | BF |
| 涉及配置 | MultiLineText | BG |
| 依赖层文档 | Url | BH |
| 研发介入时间 | Date | BI |
| 提测时间 | Date | BJ |
| 上线时间 | Date | BK |
| 需求日志文档 | Url | BL |
| 附件 | Attachment | BM |
| 备注 | MultiLineText | BN |

状态可选值：`待评估` / `研发中` / `联调中` / `提测` / `待上线` / `已上线` / `搁置`

---

## 操作流程

### 1. 新增需求

使用 `scripts/req_add.py`：

```bash
python3 skills/req-tracker/scripts/req_add.py \
  --name "节点亲和性调度" \
  --ezone "https://ezone.ksyun.com/card/xxx" \
  --prd "https://kdocs.cn/l/xxx" \
  --pm "静鑫" \
  --date "2026-04-22"
```

脚本会：
1. 在**需求详情**表创建详情记录，拿到 record_id
2. 在 `需求日志文档/YYYY-QN/MM-DD-[需求名称].otl` 创建日志文档（含模板）
3. 将日志文档 URL 写入详情记录
4. 在**需求总览**表创建总览记录，含详情记录 ID

可选参数：`--dev`（依赖方研发）、`--frontend`（前端同学）、`--projects`（涉及项目）、`--config`（涉及配置）、`--dep-doc`（依赖层文档 URL）、`--status`（初始状态，默认"待评估"）

### 2. 更新需求状态 / 时间节点

使用 `scripts/req_update.py`：

```bash
# 更新状态
python3 skills/req-tracker/scripts/req_update.py --name "节点亲和性调度" --status "提测" --date-field "提测时间" --date "2026-04-25"

# 只更新状态
python3 skills/req-tracker/scripts/req_update.py --name "节点亲和性调度" --status "研发中"
```

脚本会同时更新总览表状态和详情表对应时间字段。

### 3. 查询需求列表

```bash
python3 skills/req-tracker/scripts/req_list.py [--status 研发中]
```

输出总览表所有（或指定状态）需求的名称、状态、Ezone卡片链接。

### 4. 追加会议/群聊日志

```bash
python3 skills/req-tracker/scripts/req_log.py \
  --name "节点亲和性调度" \
  --content "### 2026-04-22 会议\n- 决策：接口参数整合至结构体\n- 会议ID: abc123"
```

脚本找到该需求的日志文档 URL，用 `wps-dailyoffice.write_doc(action=append)` 追加内容。

### 5. 获取需求详情

```bash
python3 skills/req-tracker/scripts/req_get.py --name "节点亲和性调度"
```

---

## 季度文件夹管理

```python
def get_quarter_folder_id(date_str):
    """根据日期返回对应季度文件夹 ID，不存在则自动创建"""
    # Q1: 01-03, Q2: 04-06, Q3: 07-09, Q4: 10-12
    month = int(date_str[5:7])
    q = (month - 1) // 3 + 1
    year = date_str[:4]
    key = f"{year}-Q{q}"
    if key in QUARTER_FOLDERS:
        return QUARTER_FOLDERS[key]
    # 创建新季度文件夹（调用 file.create_in_folder）并更新配置
    ...
```

新季度文件夹创建后，手动更新本文件 `QUARTER_FOLDERS` 字典，或由 `req_add.py` 自动写入 `references/quarters.json`。

---

## 常用 mcporter 命令参考

详见 `references/api_notes.md`。

---

## 注意事项

- `wps365.dbsheet.create_records` 的 `fields_value` 必须是 **JSON 字符串**（不是对象）
- `wps365.dbsheet.create_sheet` 必须同时传 `views` 参数，否则报 "Views are empty"
- 字段类型：选择字段用 `SingleSelect`（不是 `select`），链接字段用 `url`，附件用 `attachment`
- `write_doc` 创建文档时用 `target_folder_id` 指定目标文件夹
- 查询记录用 `text_value: "text"` 获取可读文本
