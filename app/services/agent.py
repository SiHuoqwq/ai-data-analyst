import json as json_module
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.services.llm.factory import get_llm
from app.services.tools import ANALYSIS_TOOLS

TOOLS_BY_NAME = {t.name: t for t in ANALYSIS_TOOLS}
TOOLS_DESC = "\n".join(f"- {t.name}: {t.description}" for t in ANALYSIS_TOOLS)

SYSTEM_PROMPT = """你是一个专业的数据分析助手。你可以使用以下工具分析用户上传的数据：

{TOOLS_DESC}

工作流程：
1. 收到分析请求后，先用 data_summary 了解数据结构
2. 选择合适的工具进行分析
3. 用中文回复分析结果，简洁专业
4. 如果数据质量有问题（缺失值、异常值），主动提醒用户
5. 如果需要画图，选择合适的图表类型

注意：
- 所有工具都需要传入 file_id 参数
- file_id 会在对话开始时提供"""


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    file_id: str


class AgentController:
    def __init__(self):
        self.llm = get_llm()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("agent", self._agent_node)
        workflow.add_node("tools", self._tool_node)

        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {"tools": "tools", "end": END},
        )
        workflow.add_edge("tools", "agent")

        return workflow.compile()

    async def _agent_node(self, state: AgentState) -> dict:
        messages = state["messages"]
        file_id = state.get("file_id", "")

        system_content = SYSTEM_PROMPT.format(TOOLS_DESC=TOOLS_DESC)
        if file_id:
            system_content += f"\n\n当前数据文件的 file_id 是: {file_id}"

        formatted = [{"role": "system", "content": system_content}]

        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                content = msg.content or ""
                tool_calls = []
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        args = tc.get("args", {})
                        if isinstance(args, str):
                            try:
                                args = json_module.loads(args)
                            except (json_module.JSONDecodeError, TypeError):
                                args = {}
                        tool_calls.append({
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json_module.dumps(args, ensure_ascii=False),
                            },
                        })
                formatted.append(
                    {"role": "assistant", "content": content, "tool_calls": tool_calls}
                    if tool_calls
                    else {"role": "assistant", "content": content}
                )
            elif isinstance(msg, ToolMessage):
                formatted.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })

        tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            k: {"type": "string", "description": v.description or ""}
                            for k, v in t.args_schema.model_fields.items()
                        } if hasattr(t, "args_schema") and t.args_schema else {},
                        "required": [],
                    },
                },
            }
            for t in ANALYSIS_TOOLS
        ]

        result = await self.llm.chat(formatted, tools=tools_schema)

        ai_message = AIMessage(content=result["content"])
        if result.get("tool_calls"):
            ai_message.tool_calls = result["tool_calls"]

        return {"messages": [ai_message]}

    async def _tool_node(self, state: AgentState) -> dict:
        last_msg = state["messages"][-1]
        results = []
        for tc in last_msg.tool_calls:
            tool = TOOLS_BY_NAME.get(tc["name"])
            if tool:
                try:
                    result = tool.invoke(tc["args"])
                except Exception as e:
                    result = f"工具执行错误: {str(e)}"
                results.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        return {"messages": results}

    def _should_continue(self, state: AgentState) -> str:
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return "end"

    async def run(self, file_id: str, user_input: str, chat_history: list | None = None) -> str:
        messages = []
        if chat_history:
            messages = list(chat_history)
        messages.append(HumanMessage(content=user_input))

        initial = {"messages": messages, "file_id": file_id}
        result = await self.graph.ainvoke(initial)
        last_msg = result["messages"][-1]
        return last_msg.content

    async def run_stream(self, file_id: str, user_input: str):
        """Yield (event_type, content) tuples: ('tool', '...'), ('text', '...'), ('done', '')"""
        messages = [HumanMessage(content=user_input)]
        initial = {"messages": messages, "file_id": file_id}

        last_message_count = 0
        async for event in self.graph.astream(initial, stream_mode="values"):
            msgs = event.get("messages", [])
            new_msgs = msgs[last_message_count:]
            last_message_count = len(msgs)

            for msg in new_msgs:
                if isinstance(msg, AIMessage):
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        yield ("tool", json_module.dumps(msg.tool_calls, ensure_ascii=False))
                    if msg.content:
                        yield ("text", msg.content)
                elif isinstance(msg, ToolMessage):
                    yield ("tool_result", msg.content)

        yield ("done", "")
