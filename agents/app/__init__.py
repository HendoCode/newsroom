"""Newsroom agents service.

FastAPI app that (per docs/design.md D5, §6) will host the deterministic orchestration
state machine and the LLM-facing work. This v1 skeleton wires only /health and one stub
endpoint that the Next.js BFF calls; the state machine, LLM module, and data layer are
downstream tickets that build on the seams left here.
"""

__version__ = "0.1.0"
