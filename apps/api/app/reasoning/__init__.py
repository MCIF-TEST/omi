"""Optional LLM enhancement layer (Phase 7).

Strictly additive. LLMs never:

* make detection decisions,
* run in the scan hot path,
* are required for the product to work.

When ``OMI_ANTHROPIC_API_KEY`` is set, ``synthesize_commentary()``
calls Claude Haiku to write an analyst-style paragraph. When it
isn't, a ``TemplateProvider`` generates competent prose from the
same structured input.
"""

from app.reasoning.providers import (  # noqa: F401
    LLMProvider, ProviderResult, TemplateProvider, get_provider,
)
from app.reasoning.commentary import synthesize_commentary  # noqa: F401
