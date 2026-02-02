"""
Agent nodes for the multi-agent chat workflow.

Each module exposes a `make_*_node(...)` factory that returns a LangGraph node
callable: `(state) -> dict`.
"""

