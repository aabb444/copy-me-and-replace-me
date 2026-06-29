"""
主程序 —— Agent 交互入口
=========================
运行方式：
  python main.py                             # 交互模式
  python main.py "写一个 Python 快速排序"     # 单次执行
"""
import os
import sys
from pathlib import Path

# 加载 .env 中的 API Key
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text("utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, val = line.strip().split("=", 1)
            os.environ.setdefault(key, val)

# 加载自己的模块
sys.path.insert(0, str(Path(__file__).parent))
from agent import Agent
from tools import read_file, write_file, list_files, run_command, web_search


def create_code_assistant_agent() -> Agent:
    """创建编程助手 Agent。"""
    agent = Agent(
        system_prompt="""你是一个编程助手。你的职责：
1. 帮助用户解决编程问题、写代码、调试
2. 需要时可以读取和查看项目文件
3. 可以运行 shell 命令来验证代码
4. 给出清晰、可直接运行的代码
5. 完成时做简要总结

同时你还可以执行文件操作（读/写/列目录）和网络搜索。
优先使用 read_file 查看文件后再操作。""",
        model="claude-opus-4-8",
        max_tokens=8192,
    )

    # 注册工具
    agent.add_tool("read_file", "读取本地文件内容", read_file)
    agent.add_tool("write_file", "创建或覆盖写入文件（限项目目录内）", write_file)
    agent.add_tool("list_files", "列出目录中的文件", list_files)
    agent.add_tool(
        "run_command",
        "运行一个 shell 命令（例如 python test.py, ls, git 等）",
        run_command,
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要运行的命令"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 30"},
            },
            "required": ["command"],
        },
    )
    agent.add_tool(
        "web_search",
        "搜索网络获取实时信息",
        web_search,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        },
    )
    return agent


def interactive_mode(agent: Agent):
    """交互式命令行模式。"""
    print("=" * 60)
    print("🤖 自建 Agent 交互模式")
    print("=" * 60)
    print(f"模型: {agent.model}")
    print("指令: /reset 重置对话  /exit 退出\n")

    while True:
        try:
            user_input = input("\n🧑 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input == "/exit":
            print("再见！")
            break
        if user_input == "/reset":
            agent.reset()
            print("✅ 对话已重置")
            continue

        print("\n🤖 思考中...", end="", flush=True)
        try:
            result = agent.run(user_input)

            # 清除"思考中"提示并输出
            print("\r" + " " * 20 + "\r", end="")
            print(f"\n🤖 {result}")
        except Exception as e:
            print(f"\n❌ 错误: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="自建 Agent — Claude 驱动的自主代理")
    parser.add_argument("prompt", nargs="?", help="直接执行一条指令（不进入交互模式）")
    parser.add_argument("--model", default="claude-opus-4-8", help="Claude 模型名")
    parser.add_argument("--max-tokens", type=int, default=8192, help="最大 token 数")
    parser.add_argument("--effort", default=None, help="推理努力度: low/medium/high/xhigh/max")

    args = parser.parse_args()

    # 检查 API Key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ 未设置 ANTHROPIC_API_KEY")
        print("   方法1: 编辑 .env 文件填入你的 Key")
        print("   方法2: set ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # 创建 Agent
    agent = create_code_assistant_agent()
    if args.model:
        agent.model = args.model
    if args.max_tokens:
        agent.max_tokens = args.max_tokens

    # 单次模式或交互模式
    if args.prompt:
        kwargs = {}
        if args.effort:
            kwargs["output_config"] = {"effort": args.effort}
        result = agent.run(args.prompt, **kwargs)
        print(result)
    else:
        interactive_mode(agent)


if __name__ == "__main__":
    main()
