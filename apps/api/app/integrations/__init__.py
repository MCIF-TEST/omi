"""Platform connectors.

Each connector exposes a thin client + a normalizer that turns raw API
responses into the platform-agnostic ``Profile`` / ``Post`` schemas. The
detection layer never sees platform-specific shapes.
"""
