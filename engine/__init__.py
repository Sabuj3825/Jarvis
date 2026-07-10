# engine/__init__.py
"""
engine/
=======
JARVIS v7 dynamic intelligence layer.

Modules
-------
query_normalizer    : Normalize user input — fix typos, expand abbreviations
entity_extractor    : Extract named entities and topics from a query
source_registry     : Plugin registry for knowledge sources
knowledge_planner   : Dynamic source selector (replaces hardcoded frozensets)
confidence_engine   : Score facts for trustworthiness before caching
provider_registry   : Plugin registry for AI providers
ai_planner          : Dynamic provider selector (replaces hardcoded chains)

This layer sits ABOVE routing/ and providers/ — it never breaks them.
If any engine module fails to import, jarvis.py falls back to the legacy system.
"""
