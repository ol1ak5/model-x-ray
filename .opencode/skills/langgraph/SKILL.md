---
name: langgraph
description: Building the Model X-Ray investigation graph — verified import paths, state reducers, interrupt/resume, checkpointer, subgraphs and tool binding for langgraph 1.2.x
---

# LangGraph

Model X-Ray's agent graph is LangGraph (`docs/agent-architecture.md` is the authoritative design; this skill covers the API mechanics). Read that doc before changing node wiring.

## Versions verified in this environment (2026-10-08)

Verified against the project environment with `uv run --with langgraph --with langchain-openai --with langgraph-checkpoint-sqlite`:

| Fact | Value |
|---|---|
| langgraph | 1.2.14 |
| langchain-openai | 1.6.7 |
| `SqliteSaver` | **separate package** `langgraph-checkpoint-sqlite` (3.1.1), not in langgraph core |
| `create_react_agent` | `from langgraph.prebuilt import ToolNode, tools_condition, create_react_agent` — **`langgraph.react_agent` does NOT exist** in 1.2.14 |
| `interrupt` / `Command` | `from langgraph.types import interrupt, Command` |
| `Command` params | `graph`, `update`, `resume`, `goto` |
| `interrupt` params | `value`, `response_schema` |

## Core imports

```python
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.types import Command, interrupt
from langgraph.checkpoint.sqlite import SqliteSaver        # needs langgraph-checkpoint-sqlite
from langgraph.checkpoint.memory import InMemorySaver     # for tests
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.store.memory import InMemoryStore          # long-term memory (tests)
```

Add the dependency: `uv add langgraph langchain-openai langgraph-checkpoint-sqlite`.

## Human-in-the-loop (design: the one pause, human_review, uses this)

Old `interrupt_before=` / `NodeInterrupt` patterns are deprecated. Inside a node:

```python
decision = interrupt({"report": state["report"], "patch": state.get("patch")})
```

The graph pauses; resume from the client with:

```python
graph.invoke(Command(resume={"action": "approve"}), config)
```

`locate` interrupts only when ambiguous; `human_review` always interrupts (approve / edit / reject).

## State + reducers

`InvestigationState` is a `TypedDict`. Un-annotated keys overwrite; reducers must be deliberate:

```python
class InvestigationState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    hypotheses: Annotated[list[Hypothesis], merge_by_id]
    verifications: Annotated[list[Verification], operator.add]
    evidence: Annotated[list[Evidence], operator.add]
    target: TargetCell | None          # overwrite
    attempts: int                      # overwrite, incremented by verify
```

`merge_by_id` is custom: update a hypothesis's status in place, append new ids, never duplicate. Full schema and reducer rationale: `docs/agent-architecture.md` §State.

## Wiring

```python
g = StateGraph(InvestigationState)
g.add_node("trace", trace_node)                 # node fn: (state) -> partial state, or Command
g.add_edge(START, "load_sheet")
g.add_conditional_edges("verify", route_after_verify, {
    "confirmed": "explain", "retry": "diagnose", "inconclusive": "explain",
})
graph = g.compile(checkpointer=SqliteSaver.from_conn_string("xray.db"))
```

Routing is on structured state fields (was the fix verified? attempts < 3?), never on parsing messages.

- Config for a run: `{"configurable": {"thread_id": "<investigation id>"}}` — one thread per investigation; the checkpointer stores full state after every node (enables resume + time travel).
- Subgraphs (Investigator) carry their own private message history so tool calls don't pollute the user conversation; only the structured `hypotheses` land in the parent state.
- Long-term memory: `BaseStore` on the compiled graph, namespaces `("models", spreadsheet_id)`, `("findings", ...)`, `("overrides", ...)`; `InMemoryStore` in tests.

## Tool calling with Nemotron

```python
llm = ChatOpenAI(model=MODEL, base_url=BASE_URL, api_key=key)   # base_url IS a param (verified)
llm.bind_tools(tools)                                           # OpenAI tools format
```

`ToolNode` executes; `tools_condition` routes. Tools must be read-only for the Investigator — write tools live only in code nodes (`test`, `apply_fix`), never bound to an LLM.

## Testing patterns (no unitary tests — deep tests only, AGENTS.md)

- Pause/resume: run until interrupt with `InMemorySaver`, assert the interrupt payload, resume with `Command`, assert the tail.
- Retry loop: fake LLM whose tool calls/verdicts are scripted; assert the full `diagnose → test → verify → diagnose` cycle and the terminal inconclusive path.
- Fixtures: real spreadsheet fixtures, not mocked Sheets responses, except the single live opt-in test.

## Docs

https://langchain-ai.github.io/langgraph/ (fetch before relying on anything not verified above; pin behavior to the installed version when they disagree).
