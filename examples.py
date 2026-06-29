"""
高级用法示例
=============
展示 Agent 引擎的不同配置和使用方式。
运行: python examples.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agent import Agent
from tools import read_file, run_command, web_search


def example_simple_qa():
    """例 1: 简单问答（无工具调用）。"""
    print("\n" + "=" * 60)
    print("示例 1: 简单问答（无工具）")
    print("=" * 60)

    agent = Agent(system_prompt="你用最简洁的方式回答问题。")
    result = agent.run("Python 中如何合并两个字典？给我一行代码")
    print(f"\n回答:\n{result}")


def example_code_assistant():
    """例 2: 编程助手（使用文件/命令工具）。"""
    print("\n" + "=" * 60)
    print("示例 2: 编程助手")
    print("=" * 60)

    agent = Agent(
        system_prompt="""你是 Python 编程助手。写代码、保存到文件、运行测试。
完成时总结你做了什么。""",
    )
    agent.add_tool("read_file", "读文件", read_file)
    agent.add_tool("run_command", "运行命令", run_command)

    result = agent.run("用 Python 写一个斐波那契数列生成器，保存为 fib.py，然后运行它 n=10")
    print(f"\n回答:\n{result}")


def example_with_thinking():
    """例 3: 启用高级推理（adaptive thinking + effort）。"""
    print("\n" + "=" * 60)
    print("示例 3: 高级推理模式")
    print("=" * 60)

    agent = Agent()
    result = agent.run(
        "设计一个简单的任务队列系统，分析其优缺点",
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
    )
    print(f"\n回答:\n{result}")


def example_research():
    """例 4: 研究助手（带搜索）。"""
    print("\n" + "=" * 60)
    print("示例 4: 研究助手（网络搜索）")
    print("=" * 60)

    agent = Agent(
        system_prompt="""你是研究助手。搜索网络获取信息，然后给出有引用来源的回答。
不要编造信息。如果搜索不到，就说不知道。""",
    )
    agent.add_tool("web_search", "搜索网络获取实时信息", web_search)

    result = agent.run("2025-2026 年 Python 生态有什么重要的新变化？")
    print(f"\n回答:\n{result}")


if __name__ == "__main__":
    # 默认只跑第一个示例演示
    # 修改下面的注释来切换
    example_simple_qa()
    # example_code_assistant()
    # example_with_thinking()
    # example_research()
