"""
实用工具集合 —— Agent 可以调用的各种工具函数
"""
import subprocess
import json
from pathlib import Path


def read_file(path: str) -> str:
    """读取本地文件内容。

    Args:
        path: 文件路径
    """
    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"错误: 文件 {path} 不存在"
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"读取失败: {e}"


def write_file(path: str, content: str) -> str:
    """写入或创建文件。

    Args:
        path: 文件路径
        content: 文件内容
    """
    try:
        p = Path(path).resolve()
        # 安全限制：只允许在项目目录内写入
        allowed = Path.cwd().resolve()
        if allowed not in p.parents and p != allowed:
            return f"错误: 不允许在项目目录外写入: {path}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"已写入 {path} ({len(content)} 字符)"
    except Exception as e:
        return f"写入失败: {e}"


def list_files(path: str = ".") -> str:
    """列出目录内容。

    Args:
        path: 目录路径
    """
    try:
        p = Path(path).resolve()
        if not p.is_dir():
            return f"错误: {path} 不是目录"
        items = []
        for entry in p.iterdir():
            kind = "📁" if entry.is_dir() else "📄"
            items.append(f"{kind} {entry.name}")
        return "\n".join(items) if items else "(空目录)"
    except Exception as e:
        return f"列表失败: {e}"


def run_command(command: str, timeout: int = 30) -> str:
    """运行一个 shell 命令。

    Args:
        command: 要运行的命令
        timeout: 超时秒数
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = []
        if result.stdout:
            output.append(result.stdout.rstrip())
        if result.stderr:
            output.append(f"[stderr]\n{result.stderr.rstrip()}")
        return "\n".join(output) if output else "(无输出)"
    except subprocess.TimeoutExpired:
        return f"错误: 命令超时 ({timeout}s)"
    except Exception as e:
        return f"执行失败: {e}"


def web_search(query: str) -> str:
    """搜索网络获取实时信息（使用命令行工具）。

    Args:
        query: 搜索关键词
    """
    try:
        import httpx
        # 使用 DuckDuckGo 的轻量搜索 API
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        resp = httpx.get(url, params=params, timeout=10)
        data = resp.json()
        results = []
        # Abstract text
        if data.get("AbstractText"):
            results.append(data["AbstractText"])
        # Related topics
        for topic in data.get("RelatedTopics", [])[:5]:
            if "Text" in topic:
                results.append(topic["Text"])
            elif "Topics" in topic:
                for sub in topic["Topics"][:3]:
                    if "Text" in sub:
                        results.append(sub["Text"])
        return "\n".join(results) if results else "未找到相关信息"
    except ImportError:
        return "需要安装 httpx: pip install httpx"
    except Exception as e:
        return f"搜索失败: {e}"
