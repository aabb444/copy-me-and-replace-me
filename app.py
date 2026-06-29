"""
Flask Web 服务器 —— 笔记/任务/日历管理界面
========================================
运行: python app.py
访问: http://localhost:5000
"""
import sys
import os
from pathlib import Path

# 确保能找到 agent 目录
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template, request, jsonify, Response
from datetime import datetime, date
import calendar

from storage import (
    load_active_tasks, complete_task, get_calendar_data,
    get_all_tags, get_notes_by_tag, search_notes,
    get_tasks_by_date, get_archived_tasks,
)
from note_task_agent import create_task_from_text, process_note
from rag import build_rag_context, index_vault, search_vault

app = Flask(__name__)


# ═══════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════

@app.route("/")
def index():
    """主页面。"""
    now = datetime.now()
    cal_data = get_calendar_data(now.year, now.month)
    tasks = load_active_tasks()
    tags = get_all_tags()

    # 按优先级排序
    priority_order = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda t: (
        priority_order.get(t.get("priority", "medium"), 1),
        t.get("time", ""),
    ))

    return render_template(
        "index.html",
        calendar=cal_data,
        tasks=tasks,
        tags=tags,
        today=date.today().isoformat(),
    )


# ═══════════════════════════════════════
# API — 任务
# ═══════════════════════════════════════

@app.route("/api/task", methods=["POST"])
def api_create_task():
    """AI 解析自然语言并创建任务。"""
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "请输入任务内容"}), 400

    try:
        task = create_task_from_text(text)
        return jsonify({"success": True, "task": task})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/task/<task_id>/complete", methods=["PATCH"])
def api_complete_task(task_id):
    """完成任务。"""
    if complete_task(task_id):
        return jsonify({"success": True})
    return jsonify({"error": "任务不存在"}), 404


@app.route("/api/tasks/active", methods=["GET"])
def api_get_active_tasks():
    """获取所有未完成任务。"""
    tasks = load_active_tasks()
    priority_order = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda t: (
        priority_order.get(t.get("priority", "medium"), 1),
        t.get("time", ""),
    ))
    return jsonify(tasks)


@app.route("/api/tasks/date", methods=["GET"])
def api_get_tasks_by_date():
    """获取某天的任务。"""
    d = request.args.get("date", date.today().isoformat())
    active = get_tasks_by_date(d)
    archived = get_archived_tasks(d[:7])
    return jsonify({"active": active, "archived": archived})


# ═══════════════════════════════════════
# API — 日历
# ═══════════════════════════════════════

@app.route("/api/calendar", methods=["GET"])
def api_get_calendar():
    """获取月历数据。"""
    year = request.args.get("year", type=int, default=datetime.now().year)
    month = request.args.get("month", type=int, default=datetime.now().month)
    return jsonify(get_calendar_data(year, month))


# ═══════════════════════════════════════
# API — 笔记
# ═══════════════════════════════════════

@app.route("/api/note", methods=["POST"])
def api_create_note():
    """AI 分析笔记内容，生成标签并保存。"""
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "请输入笔记内容"}), 400

    try:
        note = process_note(text)
        return jsonify({"success": True, "note": note})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes", methods=["GET"])
def api_get_notes():
    """搜索笔记。"""
    query = request.args.get("query", "")
    tag = request.args.get("tag", "")

    if tag:
        notes = get_notes_by_tag(tag)
    else:
        notes = search_notes(query=query)

    return jsonify(notes)


@app.route("/api/notes/all", methods=["GET"])
def api_get_all_notes():
    """获取所有笔记（按日期倒序）。"""
    notes = search_notes()
    return jsonify(notes)


@app.route("/api/notes/search", methods=["GET"])
def api_search_notes():
    """全文搜索笔记。"""
    query = request.args.get("q", "").strip()
    notes = search_notes(query=query)
    return jsonify(notes)


@app.route("/api/note/<filename>", methods=["GET"])
def api_get_note(filename):
    """读取单篇笔记全文。"""
    from storage import read_note
    note = read_note(filename)
    if note:
        return jsonify(note)
    return jsonify({"error": "笔记不存在"}), 404


# ═══════════════════════════════════════
# API — 标签
# ═══════════════════════════════════════

@app.route("/api/tags", methods=["GET"])
def api_get_tags():
    """获取所有标签及统计。"""
    return jsonify(get_all_tags())


@app.route("/api/tags/<tag>/notes", methods=["GET"])
def api_get_tag_notes(tag):
    """获取某个标签下的所有笔记。"""
    return jsonify(get_notes_by_tag(tag))


# ═══════════════════════════════════════
# API — 本地模型聊天
# ═══════════════════════════════════════

import subprocess
import json as json_lib

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """调用本地 Ollama 模型对话（流式 SSE），带 RAG 增强。"""
    data = request.get_json()
    messages = data.get("messages", [])
    model = data.get("model", "qwen3.5-122b")
    use_rag = data.get("use_rag", True)

    # 如果是第一轮且启用 RAG，构建上下文
    last_msg = messages[-1]["content"] if messages else ""
    rag_context = ""
    if use_rag and len(messages) <= 2 and last_msg:
        from rag import build_rag_context
        rag_context = build_rag_context(last_msg)

    import httpx
    import json as j
    from flask import stream_with_context, Response as FlaskResponse

    # 如果有 RAG 上下文，注入到系统提示
    rag_messages = list(messages)
    if rag_context:
        rag_messages.insert(0, {
            "role": "system",
            "content": f"You are a knowledge base assistant. Reference the following local notes to answer.\n\n{rag_context}",
        })

    def generate():
        nonlocal rag_messages
        with httpx.Client(timeout=300) as client:
            with client.stream(
                "POST", "http://localhost:11434/api/chat",
                json={"model": model, "messages": rag_messages, "stream": True,
                      "options": {"num_gpu": 1}, "keep_alive": "5m"},
            ) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = j.loads(line)
                    except:
                        continue
                    delta = chunk.get("message", {}).get("content", "")
                    if delta:
                        yield f"data: {j.dumps({'text': delta, 'done': False})}\n\n"
                    if chunk.get("done"):
                        yield f"data: {j.dumps({'text': '', 'done': True})}\n\n"
                        break

    return FlaskResponse(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                             "Connection": "keep-alive"})


@app.route("/api/models", methods=["GET"])
def api_models():
    """获取本地可用的模型列表。"""
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        models = []
        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if parts:
                models.append(parts[0])
        return jsonify(models)
    except Exception as e:
        return jsonify([])


@app.route("/api/note-from-chat", methods=["POST"])
def api_note_from_chat():
    """将聊天内容保存为笔记。"""
    data = request.get_json()
    title = data.get("title", "聊天记录")
    content = data.get("content", "")
    if not content:
        return jsonify({"error": "内容为空"}), 400

    from storage import save_note
    filename = save_note(
        title=title,
        content=content,
        tags=["chat-record"],
        note_type="chat",
    )
    return jsonify({"success": True, "filename": filename})


@app.route("/api/index-vault", methods=["POST"])
def api_index_vault():
    """重建向量索引。"""
    from rag import index_vault
    result = index_vault()
    return jsonify(result)

if __name__ == "__main__":
    # 检查 API Key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            for line in env_file.read_text("utf-8").splitlines():
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.strip().split("=", 1)
                    if k == "ANTHROPIC_API_KEY" and v:
                        api_key = v
                        os.environ["ANTHROPIC_API_KEY"] = v

    if not api_key:
        print("未设置 ANTHROPIC_API_KEY")
        print("请编辑 .env 或设置环境变量")
        sys.exit(1)

    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", 5001, app, use_reloader=False, use_debugger=True, threaded=True)
