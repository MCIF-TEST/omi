"""Memory / self-improving layer.

Turns every scan into a fixed-width behavioral fingerprint, persists it, and
lets future scans pull a prior probability from the nearest-neighbor set of
previously-scored accounts.

This is what gives Omi the "the platform gets smarter as more people use it"
property. The detection layer remains pure; this module is the only place
that combines detector outputs with the persistent fingerprint store.
"""

from app.memory.fingerprint import extract_fingerprint, FINGERPRINT_DIM
from app.memory.prior import compute_memory_signal

__all__ = ["extract_fingerprint", "FINGERPRINT_DIM", "compute_memory_signal"]
