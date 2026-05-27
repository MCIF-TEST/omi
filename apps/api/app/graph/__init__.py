"""Graph + coordination intelligence — Phase 4.

Promotes the engine's per-scan coordination clusters into a persistent,
cumulative graph that we can query across time.

Architecture:
    GraphStore       (app/graph/store.py)        — read/write edge records
    graph_algorithms (app/graph/algorithms.py)   — networkx wrappers
    GraphService     (app/graph/service.py)      — high-level API
    routes/graph     (app/routes/graph.py)       — HTTP layer

The store is abstracted so a future PR can swap Postgres → Neo4j without
touching service or routes.
"""

from app.graph.store import GraphStore  # noqa: F401
from app.graph.service import GraphService  # noqa: F401
