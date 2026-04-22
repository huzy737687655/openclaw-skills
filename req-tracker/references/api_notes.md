# WPS API 使用注意事项

## 多维表（DBSheet）

### 记录操作
- `create_records` / `update_records` 的 `fields_value` 必须是 **JSON 字符串**，不是对象
  ```python
  "fields_value": json.dumps({"需求名称": "xxx"}, ensure_ascii=False)
  ```
- `list_records` 加 `text_value: "text"` 返回可读文本（否则返回原始格式）
- 返回的 `fields` 字段也是 JSON 字符串，需要 `json.loads()` 解析

### 字段类型
| 用途 | 正确类型名 | 错误写法 |
|------|-----------|---------|
| 单选 | `SingleSelect` | `select` |
| 链接 | `url` | `link_url` |
| 附件 | `attachment` | `file` |
| 文本 | `text` | `string` |
| 日期 | `date` | `datetime` |

### create_sheet 必须传 views
```python
body = {
    "name": "表名",
    "views": [{"name": "默认视图", "view_type": "Grid"}],  # ← 必须！否则报 "Views are empty"
    "fields": [...]
}
```

## 云文档（write_doc）

### 创建文档到指定文件夹
```python
mcpcall("wps-dailyoffice.write_doc",
    action="create",
    name="文档名（不含扩展名）",
    doc_type="doc",
    content_markdown=content,
    target_folder_id="文件夹ID")
```
- 不支持直接用 `file.create_in_folder` 创建文档（会报 400 参数不支持）
- 文档创建后返回 `file.link_url`（`https://www.kdocs.cn/l/xxx`）和 `file.id`

### 追加内容
```python
mcpcall("wps-dailyoffice.write_doc",
    action="append",
    file_id="文档ID",
    content_markdown="追加的内容")
```

## 文件夹操作

### 创建文件夹
```python
mcpcall("ksc-mcp-wps.file.create_in_folder",
    path_params={"drive_id": DRIVE_ID, "parent_id": 父文件夹ID},
    body={"name": "文件夹名", "file_type": "folder", "on_name_conflict": "fail"})
```
- `file_type` 必须是 `"folder"`，不支持 `"file"` 类型（文档需用 write_doc 创建）

### 移动文件（同 drive）
```python
mcpcall("ksc-mcp-wps.file.batch_move",
    path_params={"drive_id": DRIVE_ID},
    body={"ids": ["file_id"], "to": {"drive_id": DRIVE_ID, "parent_id": "目标文件夹ID"}})
```
- 跨 drive 移动可能不支持

## 搜索文件
```python
mcpcall("ksc-mcp-wps.mcp_yundoc.search", body={"keyword": "关键词", "page_size": 10})
# 返回 result.content[0].text（JSON 字符串）中的 items 列表
```
