"""Client SDK for the Agent Observability API. Standard library only.

    from agent_observability import ObservabilityClient

    client = ObservabilityClient("http://127.0.0.1:8000", api_key="dev-local-key")
    client.register_agent("my-agent", tools=["search", "fetch"], model="gpt-4.1")

    with client.run("my-agent", task="Answer the user's question") as run:
        while True:
            ...  # your agent decides and executes a tool call
            verdict = run.tool_call("search", {"query": q}, output=result,
                                    input_tokens=usage.input, output_tokens=usage.output)
            if verdict.should_stop:
                break                      # policy says terminate / ask a human
            if verdict.action == "reflect":
                messages.append(REFLECTION_PROMPT)
        run.final_answer(answer)
"""
from .client import Assessment, LiveRun, ObservabilityClient, ObservabilityError

__all__ = ["ObservabilityClient", "LiveRun", "Assessment", "ObservabilityError"]
