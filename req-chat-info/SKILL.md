---
name: req-chat-info
description: 从需求沟通群中自动提取结构化需求信息。输入群名关键词，自动搜索群ID、拉取近期聊天记录，识别PRD文档、Ezone卡片链接、产品经理/前端/研发等人员角色，输出可直接用于录入需求台账的结构化结果。当用户说"从群里获取需求信息"、"帮我看看这个需求群"、"提取群里的需求信息"、"这个需求群叫XXX"时触发。可与 req-tracker skill 配合使用。
---

# req-chat-info — 需求群信息提取 Skill

从需求沟通群中自动提取结构化需求信息，作为录入需求台账的前置步骤。

---

## 使用方式

```bash
python3 skills/req-chat-info/scripts/extract.py \
  --group-name "支持物理队列 AICP-2652" \
  [--days 7] \
  [--output human|json]
```

| 参数 | 说明 | 默认 |
|------|------|------|
| `--group-name` | 群名关键词 | 必填 |
| `--days` | 拉取最近几天的消息 | 7 |
| `--output` | 输出格式：human（可读）或 json（结构化） | human |

---

## 执行逻辑

### Step 1 — 搜索群聊
调用 `mcp_message.search_chats`，按关键词找群 ID。
- **唯一匹配** → 直接使用
- **多个匹配** → 列出所有结果，让用户确认

### Step 2 — 解析群名中的 Ezone 卡片
正则匹配群名中的 `[A-Z]+-\d+` 格式：
```
【支持物理队列 AICP-2652】需求沟通群
                ↓
https://ezone.ksyun.com/project/AICP/2652
```

### Step 3 — 拉取聊天记录
调用 `mcp_message.get_chat_messages`，拉取近 N 天消息，解析：
- `rich_text` 消息中的内嵌云文档（`doc` 类型元素）
- `text` 消息中的 URL（kdocs / figma / ezone 链接）
- 每条消息的发送者姓名、发送时间

### Step 4 — 识别 PRD 文档
1. 优先从消息中找名称含 "PRD" 的内嵌云文档
2. 若无，调用 `mcp_yundoc.search` 搜索云文档库

### Step 5 — 推断人员角色
按发言内容关键词判断（注意 UI 同学 ≠ 前端同学）：

| 角色 | 判断依据 |
|------|---------|
| 产品经理 | 发过 PRD / 需求文档 / 评审 / OpenAPI定义 等内容 |
| UI同学 | 发过 Figma / 设计稿 / 交互设计 / UI稿 / 视觉 等内容 |
| 前端同学 | 发过 联调 / 页面问题 / 组件 / vue / react 等内容 |
| 依赖方研发 | 发过 API文档 / 接口文档 / 实现方案 / 后端 等内容 |
| 测试 | 发过 测试用例 / QA / 提测 / 测试报告 等内容 |

> ⚠️ 角色推断基于关键词，**准确率有限**，建议人工核对

### Step 6 — 文档分类，映射到台账字段

所有从群里找到的文档（内嵌云文档 + 文本中的 URL）按以下规则分类：

| 文档类型 | 识别依据 | 映射台账字段 |
|---------|---------|------------|
| PRD文档 | 名称含 PRD / 需求文档 | `PRD文档`（总览） |
| UI设计稿 | Figma/MasterGo 链接，或名称含 设计稿/UI | `UI设计稿`（日志文档记录） |
| 依赖层文档 | 名称含 API文档/接口文档/实现方案/控制台实现/OpenAPI | `依赖层文档`（详情） |
| Ezone卡片 | ezone.ksyun.com 域名 | `Ezone卡片`（总览） |
| 附件 | 其他 | `附件`（详情） |

> UI设计稿不直接映射到 `req_add.py` 参数（台账无此字段），会提示追加到需求日志文档。

---

## 输出示例

```
需求名称:  支持物理队列 AICP-2652
Ezone卡片: https://ezone.ksyun.com/project/AICP/2652
PRD文档:   https://www.kdocs.cn/l/ck30r0CZM9UD
产品经理:  杨凯文

参与人员:
  - 杨凯文 (产品经理)
  - 徐彤昊 (前端)
  - 孔尧 (研发)

群内文档:
  [kdoc] 【PRD】支持物理队列.otl
    https://www.kdocs.cn/l/ck30r0CZM9UD
    发送人: 杨凯文 @ 2026-04-10 19:55
  [figma] Figma设计稿
    https://www.figma.com/design/...
    发送人: 徐彤昊 @ 2026-04-08 11:35

─── 可直接用于 req-tracker 的参数 ───
python3 skills/req-tracker/scripts/req_add.py \
  --name "支持物理队列 AICP-2652" \
  --ezone "https://ezone.ksyun.com/project/AICP/2652" \
  --prd "https://www.kdocs.cn/l/ck30r0CZM9UD" \
  --pm "杨凯文" \
  --status "待评估"
```

---

## 与 req-tracker 的配合

```
用户说"从群【XXX需求群】录需求"
  ↓
req-chat-info: extract.py 提取信息
  ↓
（我确认/补充缺失字段）
  ↓
req-tracker: req_add.py 录入台账
```

---

## 依赖

- `wps-cli` skill（mcporter 调用 WPS 消息/云文档 API）
- mcporter 配置路径：`skills/wps-cli/mcporter.json`

---

## 注意事项

- 角色推断基于关键词，**准确率有限**，建议人工核对产品经理字段
- `rich_text` 消息中的内嵌 doc 元素有时不带 URL，此时会 fallback 到云文档搜索
- 若群消息较少（新群），建议增大 `--days` 参数
