---
name: req-tracker
description: 需求管理台账操作技能。用于在 WPS 多维表中管理研发需求全生命周期，包括：新增需求（自动创建总览记录+详情记录+需求日志文档）、更新需求状态或关键时间节点、查询需求列表或详情、从会议纪要/群聊自动追加日志到需求日志文档。当用户说"新增需求"、"更新需求状态"、"查看需求列表"、"把会议内容写进需求日志"、"需求提测了"、"需求上线了"等与需求跟踪相关的操作时触发。
---

# 需求管理台账 Skill

## 首次配置

复制 `config.example.json` 为 `config.json`，填入真实的 WPS ID：

```bash
cp req-tracker/config.example.json req-tracker/config.json
# 编辑 config.json，填入 DRIVE_ID、DB_FILE_ID 等
```

`config.json` 已加入 `.gitignore`，不会提交到 git。

---

## 字段结构

**需求总览（SHEET_OVERVIEW）**
| 字段 | 类型 | 字段ID |
|------|------|--------|
| 需求名称 | MultiLineText | V |
| Ezone卡片 | Url | W |
| PRD文档 | Url | X |
| 需求提出时间 | Date | Y |
| 当前状态 | SingleSelect | Z |
| 详情记录ID | MultiLineText | 0 |

**需求详情（SHEET_DETAIL）**
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

```bash
python3 skills/req-tracker/scripts/req_add.py \
  --name "节点亲和性调度" \
  --ezone "https://ezone.ksyun.com/card/xxx" \
  --prd "https://kdocs.cn/l/xxx" \
  --pm "产品经理姓名" \
  --date "2026-04-22"
```

脚本会：
1. 在**需求详情**表创建详情记录
2. 在 `需求日志文档/YYYY-QN/MM-DD-[需求名称].otl` 创建日志文档（含模板）
3. 将日志文档 URL 写入详情记录
4. 在**需求总览**表创建总览记录

可选参数：`--dev`、`--frontend`、`--projects`、`--config`、`--dep-doc`、`--status`（默认"待评估"）

### 2. 更新需求状态 / 时间节点

```bash
python3 skills/req-tracker/scripts/req_update.py --name "需求名称" --status "提测" --date-field "提测时间" --date "2026-04-25"
```

### 3. 查询需求列表

```bash
python3 skills/req-tracker/scripts/req_list.py [--status 研发中]
```

### 4. 追加会议/群聊日志

```bash
python3 skills/req-tracker/scripts/req_log.py \
  --name "需求名称" \
  --content "### 2026-04-22 会议\n- 决策：xxx\n- 会议ID: abc123"
```

### 5. 获取需求详情

```bash
python3 skills/req-tracker/scripts/req_get.py --name "需求名称"
```

---

### 6. 会议归档（定时 / 手动触发）

**每天 18:00 自动运行**，或你说"帮我归档今天的会议"时触发。

```bash
# Step1: 拉取当天会议，输出 pending 列表
python3 skills/req-tracker/scripts/req_meeting_sync.py

# Step2: 我解析你的回复后，调用确认脚本
python3 skills/req-tracker/scripts/req_meeting_confirm.py \
  --replies '{"会议ID1":"需求名称","会议ID2":"忽略"}'
```

**本地归档文件** `references/meeting_archive.json`（map 结构，会议ID为key）：
```json
{
  "meetings": {
    "abc123": {"title":"评审会","date":"2026-04-22","status":"archived","req_name":"节点亲和性调度"},
    "xyz456": {"title":"周例会","date":"2026-04-22","status":"ignored","req_name":null}
  },
  "last_sync": "2026-04-22T18:00:00"
}
```

状态值：`pending`（待确认）/ `archived`（已归档）/ `ignored`（无需归档）

保留天数由 `config.json` 的 `MEETING_ARCHIVE_DAYS` 控制（默认 3 天）。

**问询格式**（批量，每批 5 条）：
```
📋 发现 N 条未归档会议，分 X 批确认

── 第 1 批 ──
1. [14:00] 节点亲和性调度评审（45分钟）
2. [15:00] 周例会（60分钟）
...
回复格式：1-需求名称 2-忽略 ...
```

---

## 季度文件夹管理

`references/quarters.json` 记录各季度文件夹 ID（不含敏感信息时可提交）。
新季度时 `req_add.py` 会自动创建并更新该文件。

---

## 常用 mcporter 命令参考

详见 `references/api_notes.md`。

---

## 注意事项

- `wps365.dbsheet.create_records` 的 `fields_value` 必须是 **JSON 字符串**
- `wps365.dbsheet.create_sheet` 必须同时传 `views` 参数
- 字段类型：选择字段用 `SingleSelect`，链接字段用 `url`
- `write_doc` 创建文档时用 `target_folder_id` 指定目标文件夹
