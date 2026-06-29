"""
存储层 —— 所有文件系统读写操作
================================
提供统一的接口操作：
  - vault/   : 笔记（Markdown）
  - tasks/   : 任务（JSON）
  - schedule/: 日历（JSON）
  - tags     : 标签索引（JSON）
"""
import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

# 基础路径
CODEX_DIR = Path.home() / ".codex"
VAULT_DIR = CODEX_DIR / "vault"
TASKS_DIR = CODEX_DIR / "tasks"
SCHEDULE_DIR = CODEX_DIR / "schedule"
TAGS_FILE = CODEX_DIR / "vault" / "tags.json"

# 确保目录存在
for d in [VAULT_DIR / "daily", VAULT_DIR / "topics", VAULT_DIR / "summaries",
          TASKS_DIR / "archive", SCHEDULE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════
# 笔记操作
# ═══════════════════════════════════════

def save_note(title: str, content: str, tags: list[str],
              note_type: str = "note", status: str = "active") -> str:
    """保存一篇笔记到 vault/topics/，返回文件名。"""
    # 清理标题做文件名
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    safe_title = safe_title.strip().replace(" ", "-")[:80]
    filename = f"{safe_title}.md"
    filepath = VAULT_DIR / "topics" / filename

    # 构建 frontmatter
    frontmatter = {
        "title": title,
        "date": date.today().isoformat(),
        "tags": tags,
        "type": note_type,
        "status": status,
    }

    # 写入文件
    md = "---\n"
    for k, v in frontmatter.items():
        if isinstance(v, list):
            md += f"{k}:\n"
            for item in v:
                md += f"  - {item}\n"
        else:
            md += f"{k}: {v}\n"
    md += "---\n\n"
    md += content
    md += "\n"

    filepath.write_text(md, encoding="utf-8")

    # 更新标签索引
    _update_tag_index(tags, filename)

    return filename


def read_note(filename: str) -> Optional[dict]:
    """按文件名读取笔记内容。"""
    for subdir in ["topics", "daily", "summaries"]:
        fp = VAULT_DIR / subdir / filename
        if fp.exists():
            text = fp.read_text(encoding="utf-8")
            return {"filename": filename, "path": str(fp), "content": text}
    return None


def search_notes(query: str = "", tag: str = "") -> list[dict]:
    """搜索笔记。支持关键词匹配和标签过滤。

    返回 [{filename, title, tags, preview, date}, ...]
    """
    results = []
    for fp in sorted(VAULT_DIR.rglob("*.md"), reverse=True):
        text = fp.read_text(encoding="utf-8")
        meta = _parse_frontmatter(text)

        # 标签过滤
        if tag and tag not in meta.get("tags", []):
            continue

        # 关键词过滤（搜索标题和正文）
        if query:
            content_lower = text.lower()
            if query.lower() not in content_lower:
                continue

        preview = text.split("---", 2)[-1].strip()[:200] if "---" in text else text[:200]
        results.append({
            "filename": fp.name,
            "title": meta.get("title", fp.stem),
            "tags": meta.get("tags", []),
            "date": meta.get("date", ""),
            "preview": preview,
        })

    # 按日期排序（最新的在前）
    if query:
        return results
    return sorted(results, key=lambda x: x["date"], reverse=True)


# ═══════════════════════════════════════
# 任务操作
# ═══════════════════════════════════════

def load_active_tasks() -> list[dict]:
    """加载所有未完成的任务。"""
    fp = TASKS_DIR / "active.json"
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_tasks(tasks: list[dict]):
    """保存未完成任务列表。"""
    fp = TASKS_DIR / "active.json"
    fp.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def add_task(title: str, task_date: str, time: str = "",
             priority: str = "medium", tags: list[str] = None) -> dict:
    """添加新任务并同步到日历。"""
    tasks = load_active_tasks()

    now = datetime.now()
    task_id = f"task_{now.strftime('%Y%m%d_%H%M%S')}"

    task = {
        "id": task_id,
        "title": title,
        "date": task_date,
        "time": time,
        "priority": priority,
        "tags": tags or [],
        "status": "active",
        "created_at": now.isoformat(),
        "completed_at": None,
    }

    tasks.append(task)
    save_tasks(tasks)

    # 同步到日历
    _sync_task_to_schedule(task)

    return task


def complete_task(task_id: str) -> bool:
    """完成任务：从 active 移到 archive。"""
    tasks = load_active_tasks()
    for i, t in enumerate(tasks):
        if t["id"] == task_id:
            task = tasks.pop(i)
            task["status"] = "completed"
            task["completed_at"] = datetime.now().isoformat()

            # 保存到 archive
            archive_file = TASKS_DIR / "archive" / f"{task['date']}.json"
            archive = []
            if archive_file.exists():
                archive = json.loads(archive_file.read_text(encoding="utf-8"))
            archive.append(task)
            archive_file.write_text(
                json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")

            save_tasks(tasks)
            return True
    return False


def get_tasks_by_date(task_date: str) -> list[dict]:
    """获取某天的任务。"""
    tasks = load_active_tasks()
    return [t for t in tasks if t["date"] == task_date]


def get_archived_tasks(month: str) -> list[dict]:
    """获取某月的已完成任务。"""
    archive_file = TASKS_DIR / "archive" / f"{month}.json"
    if archive_file.exists():
        return json.loads(archive_file.read_text(encoding="utf-8"))
    return []


# ═══════════════════════════════════════
# 月历操作
# ═══════════════════════════════════════

def get_calendar_data(year: int, month: int) -> dict:
    """获取某月的日历数据：每天的任务数量。"""
    prefix = f"{year:04d}-{month:02d}"

    # 统计未完成任务
    tasks = load_active_tasks()
    day_counts: dict[str, int] = {}
    for t in tasks:
        if t["date"].startswith(prefix):
            day_counts[t["date"]] = day_counts.get(t["date"], 0) + 1

    # 统计已完成任务
    archive = get_archived_tasks(prefix)
    for t in archive:
        if t["date"].startswith(prefix):
            day_counts[t["date"]] = day_counts.get(t["date"], 0) + 1

    # 日历矩阵
    import calendar
    cal = calendar.Calendar()
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(None)
            else:
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                row.append({
                    "day": day,
                    "date": date_str,
                    "count": day_counts.get(date_str, 0),
                    "is_today": date_str == date.today().isoformat(),
                })
        weeks.append(row)

    return {
        "year": year,
        "month": month,
        "month_name": ["", "一月", "二月", "三月", "四月", "五月", "六月",
                       "七月", "八月", "九月", "十月", "十一月", "十二月"][month],
        "weeks": weeks,
    }


# ═══════════════════════════════════════
# 标签操作
# ═══════════════════════════════════════

def get_all_tags() -> dict:
    """获取所有标签及统计。"""
    if TAGS_FILE.exists():
        return json.loads(TAGS_FILE.read_text(encoding="utf-8"))
    return {}


def get_notes_by_tag(tag: str) -> list[dict]:
    """获取某个标签下的所有笔记。"""
    all_tags = get_all_tags()
    note_names = all_tags.get(tag, {}).get("notes", [])
    results = []
    for name in note_names:
        note = read_note(name)
        if note:
            meta = _parse_frontmatter(note["content"])
            results.append({
                "filename": name,
                "title": meta.get("title", name),
                "date": meta.get("date", ""),
                "tags": meta.get("tags", []),
                "preview": note["content"].split("---", 2)[-1].strip()[:150] if "---" in note["content"] else "",
            })
    return results


# ═══════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════

def _parse_frontmatter(text: str) -> dict:
    """从 Markdown 文本解析 frontmatter。"""
    meta = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if line.startswith("  - "):
                    # list item continuation
                    if current_key:
                        meta.setdefault(current_key, []).append(line.strip("  - "))
                    continue
                if ": " in line:
                    key, val = line.split(": ", 1)
                    key = key.strip()
                    val = val.strip()
                    if val.startswith("["):
                        # inline list
                        import ast
                        try:
                            meta[key] = ast.literal_eval(val)
                        except:
                            meta[key] = val
                    elif line.strip().startswith("- "):
                        meta.setdefault(current_key, []).append(val)
                    else:
                        meta[key] = val
                        current_key = key if line.strip().endswith(":") else None
    return meta


def _update_tag_index(tags: list[str], note_filename: str):
    """更新标签索引用新笔记。"""
    index = {}
    if TAGS_FILE.exists():
        try:
            index = json.loads(TAGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            index = {}

    for tag in tags:
        if tag not in index:
            index[tag] = {"count": 0, "notes": [], "related_tags": []}
        entry = index[tag]
        if note_filename not in entry["notes"]:
            entry["notes"].append(note_filename)
            entry["count"] = len(entry["notes"])
        # 更新相关标签
        for other in tags:
            if other != tag and other not in entry["related_tags"]:
                entry["related_tags"].append(other)

    TAGS_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _sync_task_to_schedule(task: dict):
    """将任务同步到日历 JSON。"""
    month = task["date"][:7]
    sched_file = SCHEDULE_DIR / f"{month}.json"

    schedule = []
    if sched_file.exists():
        schedule = json.loads(sched_file.read_text(encoding="utf-8"))

    schedule.append({
        "id": task["id"],
        "title": task["title"],
        "date": task["date"],
        "time": task["time"],
        "priority": task["priority"],
        "status": task["status"],
    })

    sched_file.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
