"""
Agent 核心引擎 —— 自建 Agent 的消息循环
=====================================
核心逻辑：
  1. 发消息给 Claude
  2. 如果返回 tool_use → 执行工具 → 发结果回去
  3. 如果返回 end_turn → 输出最终回答
  4. 处理 max_tokens / refusal 等边界情况
"""

import json
import logging
from typing import Any, Callable

import anthropic

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表 —— 管理所有可用的工具定义和执行函数。"""

    def __init__(self):
        self._tools: list[dict] = []
        self._handlers: dict[str, Callable] = {}

    def register(
        self,
        name: str,
        description: str,
        handler: Callable,
        input_schema: dict | None = None,
    ):
        """注册一个工具。

        Args:
            name: 工具名（必须是唯一的）
            description: 工具描述（Claude 据此决定何时调用）
            handler: 工具执行函数
            input_schema: JSON Schema（若为 None，自动从 handler 类型推断）
        """
        # 自动推断 schema（简化版：从函数参数生成）
        if input_schema is None:
            import inspect

            sig = inspect.signature(handler)
            properties = {}
            required = []
            for param_name, param in sig.parameters.items():
                # 简单类型映射
                type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
                param_type = type_map.get(
                    param.annotation if param.annotation != inspect.Parameter.empty else str,
                    "string",
                )
                properties[param_name] = {"type": param_type}
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

            input_schema = {
                "type": "object",
                "properties": properties,
                "required": required,
            }

        self._tools.append({
            "name": name,
            "description": description,
            "input_schema": input_schema,
        })
        self._handlers[name] = handler

    def get_definitions(self) -> list[dict]:
        """获取 OpenAI 格式的工具定义列表。"""
        return self._tools

    def execute(self, name: str, args: dict) -> str:
        """执行一个工具并返回结果文本。"""
        handler = self._handlers.get(name)
        if handler is None:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)

        try:
            result = handler(**args)
            # 统一转为 JSON 字符串返回
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            logger.exception(f"工具 {name} 执行失败")
            return json.dumps({"error": str(e)}, ensure_ascii=False)


class Agent:
    """自主 Agent —— 通用的 Claude 驱动代理。"""

    def __init__(
        self,
        system_prompt: str = "你是一个有用的 AI 助手。",
        model: str = "claude-opus-4-8",
        max_tokens: int = 4096,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.messages: list[dict] = []
        self.tools = ToolRegistry()

    def add_tool(
        self,
        name: str,
        description: str,
        handler: Callable,
        input_schema: dict | None = None,
    ):
        """注册一个工具给 Agent 使用。"""
        self.tools.register(name, description, handler, input_schema)

    def run(self, user_input: str, **kwargs) -> str:
        """运行 Agent：发消息 → 循环执行工具调用 → 返回最终回答。

        Args:
            user_input: 用户输入
            **kwargs: 传给 messages.create 的额外参数（如 thinking, effort 等）

        Returns:
            Claude 的最终回答文本
        """
        # 1. 添加用户消息
        self.messages.append({"role": "user", "content": user_input})

        max_turns = kwargs.pop("max_turns", 20)  # 安全限制
        turn = 0

        while turn < max_turns:
            turn += 1

            # 2. 调用 API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=self.messages,
                tools=self.tools.get_definitions() or None,
                **kwargs,
            )

            # 3. 处理各种 stop_reason
            if response.stop_reason == "refusal":
                logger.warning("请求被安全分类器拒绝")
                self.messages.append({"role": "assistant", "content": response.content})
                return "[⚠️ 请求被拒绝]"

            if response.stop_reason == "max_tokens":
                logger.warning(f"达到 max_tokens 限制 ({self.max_tokens})，答案可能不完整")
                # 追加 assistant 回复，允许继续
                self.messages.append({"role": "assistant", "content": response.content})
                # 提示 Claude 继续
                self.messages.append({
                    "role": "user",
                    "content": "请继续，你的回答被截断了。"
                })
                continue

            # 4. 检查是否有工具调用
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if not tool_use_blocks:
                # 没有工具调用 → 最终回答
                self.messages.append({"role": "assistant", "content": response.content})
                final_text = "".join(b.text for b in text_blocks)
                return final_text

            # 5. 有工具调用 — 追加 Claude 的回复后执行工具
            self.messages.append({"role": "assistant", "content": response.content})

            # 执行所有并行工具调用
            tool_results = []
            for block in tool_use_blocks:
                logger.info(f"🔧 调用工具: {block.name}({block.input})")
                result = self.tools.execute(block.name, block.input)
                logger.info(f"  结果: {result[:200]}...")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            # 一次返回所有工具结果
            self.messages.append({"role": "user", "content": tool_results})

            # 如果有文本也输出一下（Claude 可能边思考边输出）
            if text_blocks:
                for b in text_blocks:
                    print(f"\n[Claude]: {b.text}", end="")

        logger.warning(f"达到最大对话轮数 {max_turns}")
        return "[⚠️ 达到最大轮数限制]"

    def reset(self):
        """重置对话历史。"""
        self.messages = []

    def set_system_prompt(self, prompt: str):
        """替换系统提示词（注意：会刷新缓存）。"""
        self.system_prompt = prompt
