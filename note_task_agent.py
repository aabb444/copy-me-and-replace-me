"""
Agent 任务/笔记处理器 —— 调用 Claude API 进行 AI 解析
====================================================
TaskAgent:  解析自然语言任务 → 提取时间、标题、优先级
NoteAgent:  解析笔记内容 → 生成精确标签 + 格式化 Markdown
"""
import os
import json
from datetime import datetime, date

from agent import Agent
from storage import save_note, add_task


# ═══════════════════════════════════════
# TaskAgent —— 任务处理器
# ═══════════════════════════════════════

def parse_task(text: str) -> dict:
    """用 AI 解析任务文本，提取时间和结构化信息。

    返回: {title, date, time, priority, tags}
    """
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")

    agent = Agent(
        system_prompt=f"""你是一个任务解析助手。你今天的时间参考：今天日期 {today}，当前时间 {now}。

将用户的自然语言任务解析为结构化 JSON，必须包含：
- title: 任务标题（简洁，保留核心信息）
- date: 日期（YYYY-MM-DD 格式，从文本推断，如"明天"→{today}+1天）
- time: 时间（HH:MM 格式，如果提到的话，否则空字符串）
- priority: 优先级（high/medium/low 三档之一）
- tags: 标签列表（1-3个，与长城AI科技战略相关的精确标签）

只输出 JSON，不要其他文字。""",
        model="claude-haiku-4-5",
        max_tokens=512,
    )

    result = agent.run(
        f"解析这个任务: {text}",
        output_config={"format": {
            "type": "json_schema",
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "date", "time", "priority", "tags"],
                "additionalProperties": False,
            },
        }},
    )

    # 解析 JSON
    import re
    json_match = re.search(r'\{.*\}', result, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            return {
                "title": parsed.get("title", text),
                "date": parsed.get("date", today),
                "time": parsed.get("time", ""),
                "priority": parsed.get("priority", "medium"),
                "tags": parsed.get("tags", []),
            }
        except json.JSONDecodeError:
            pass

    # 兜底：直接返回基础结构
    return {
        "title": text,
        "date": today,
        "time": "",
        "priority": "medium",
        "tags": [],
    }


def create_task_from_text(text: str) -> dict:
    """从自然语言创建任务。"""
    parsed = parse_task(text)
    task = add_task(
        title=parsed["title"],
        task_date=parsed["date"],
        time=parsed["time"],
        priority=parsed["priority"],
        tags=parsed["tags"],
    )
    return task


# ═══════════════════════════════════════
# NoteAgent —— 笔记处理器
# ═══════════════════════════════════════

def process_note(text: str) -> dict:
    """用 AI 分析笔记内容，生成精确标签和结构化 Markdown。

    返回: {title, content, tags, filename}
    """
    today = date.today().isoformat()

    agent = Agent(
        system_prompt=f"""你是一个围绕「长城AI科技战略」的个人知识管理助手。

## 你的任务
把用户的笔记内容转化为结构化 Markdown 笔记，并生成精确的标签。

## 标签生成规则（核心要求）
- 每个标签必须**精确**描述笔记的具体内容
- 禁止使用宽泛标签：#AI、#技术、#笔记、#思考、#今日记录 等
- 使用具体术语：#DeepSeek-R1、#昇腾-推理性能、#智能体-工具调用-架构
- 多级标签用连字符：如 #AI芯片-昇腾-性能测试
- 战略相关标签加前缀：#长城AI科技战略-大模型选型
- 好的标签让人看到就能知道笔记在说什么

## 输出格式
输出 JSON，包含：
1. title: 笔记标题（概括核心主题）
2. content: 完整的 Markdown 正文（适当分段）
3. tags: 精确标签列表（3-6个）

只输出 JSON，不要其他文字。""",
        model="claude-haiku-4-5",
        max_tokens=1024,
    )

    result = agent.run(
        f"整理这段笔记并生成标签:\n\n{text}",
        output_config={"format": {
            "type": "json_schema",
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                        "maxItems": 6,
                    },
                },
                "required": ["title", "content", "tags"],
                "additionalProperties": False,
            },
        }},
    )

    # 解析 JSON
    import re
    json_match = re.search(r'\{.*\}', result, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            title = parsed.get("title", "笔记")
            content = parsed.get("content", text)
            tags = parsed.get("tags", [])

            # 保存到 vault
            filename = save_note(
                title=title,
                content=content,
                tags=tags,
                note_type="note",
            )

            return {
                "title": title,
                "content": content,
                "tags": tags,
                "filename": filename,
            }
        except json.JSONDecodeError:
            pass

    # 兜底
    filename = save_note(
        title=text[:40],
        content=text,
        tags=["未分类"],
    )
    return {
        "title": text[:40],
        "content": text,
        "tags": ["未分类"],
        "filename": filename,
    }
