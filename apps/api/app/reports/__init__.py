"""Report generation — Phase 6.

Renders an investigation's stored payload into:

* ``executive`` — one-page intelligence brief
* ``evidence``  — full investigative document

Output formats:

* HTML — rendered by the Next.js public route at /r/{token}
* Markdown — `render_markdown(...)`; served as text/markdown for download
* JSON — the raw payload (no transformation)

No external dependencies. Pure-Python text assembly.
"""

from app.reports.templates import (  # noqa: F401
    Template, render_markdown, build_report_view,
)
