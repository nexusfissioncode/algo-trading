"""One way to run any agent on the desk: its own instructions, its own tools, its own model,
and an answer that comes back as JSON in a fixed shape."""
import json
import sys

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, HookMatcher,
                              ResultMessage, ToolUseBlock, create_sdk_mcp_server, tool)

FAST = "claude-haiku-4-5"      # quick and cheap: reading and doing what it is told
STRONG = "claude-sonnet-5-5"   # slower and dearer: judgement


def as_tool(name, description, schema, fn):
    """A plain Python function, offered to an agent as a tool."""
    @tool(name, description, schema)
    async def run(args):
        return {"content": [{"type": "text", "text": json.dumps(fn(**args))}]}
    return run


def say(who, text):
    """What an agent is doing, as it does it - on stderr, so its answer alone can be saved."""
    print(f"  {who:<8} {text}", file=sys.stderr, flush=True)


def options_for(name, *, instructions, answer, tools=(), model=FAST, before_tool=None):
    """Everything one agent is allowed: its instructions, model, tools - and nothing else."""
    server = create_sdk_mcp_server(name, tools=list(tools))
    allowed = [f"mcp__{name}__{t.name}" for t in tools]
    # the hook watches this agent's own tools only, not the SDK's step that hands back the answer
    hooks = None
    if before_tool:
        hooks = {"PreToolUse": [HookMatcher(matcher="|".join(allowed), hooks=[before_tool])]}
    return ClaudeAgentOptions(
        system_prompt=instructions,
        model=model,
        mcp_servers={name: server} if tools else {},
        tools=[],                                     # none of Claude Code's own tools
        allowed_tools=allowed,
        permission_mode="dontAsk",                    # anything not allowed is refused, not asked
        setting_sources=[],                           # no settings files: only what is written here
        output_format={"type": "json_schema", "schema": answer},
        hooks=hooks,
        max_turns=10,
    )


async def run_agent(name, *, task, instructions, answer, tools=(), model=FAST, before_tool=None):
    """Run one agent until it is done; return its answer (a dict shaped like `answer`)."""
    options = options_for(name, instructions=instructions, answer=answer, tools=tools,
                          model=model, before_tool=before_tool)
    async with ClaudeSDKClient(options=options) as client:
        await client.query(task)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock) and block.name != "StructuredOutput":
                        say(name, f"calls {block.name.split('__')[-1]} {json.dumps(block.input)}")
            elif isinstance(msg, ResultMessage):
                if msg.is_error or msg.structured_output is None:
                    raise RuntimeError(f"{name} did not answer: {msg.subtype} {msg.result}")
                cost = msg.total_cost_usd or 0
                say(name, f"done in {msg.duration_ms / 1000:.0f} s, {model}, about ${cost:.3f}")
                return msg.structured_output
