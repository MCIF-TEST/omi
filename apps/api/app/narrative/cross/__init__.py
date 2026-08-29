"""Cross-investigation narratives.

One question asked across every customer's investigations at once: is a topic being WORKED rather
than discussed, and are the accounts on it a formation?

Design and the argument for it: ``docs/cross-investigation-narratives.md``. Read §1 before touching
anything here, because the whole system is built to measure one difference (one customer's interest
against several unrelated customers' independent arrival) and measuring it wrong is an expensive way
to rediscover what a single user was already curious about.

Admin-only, always. These findings are assembled from many customers' scans and belong to none of
them, the same reason `/campaigns` and `/narratives` are gated.
"""
