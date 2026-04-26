"""Stable Odoo external IDs (``__import__.*``) to avoid name_search duplicates."""

import hashlib

XML_MOD = "__import__"


def categ_xid(tier, root_display, *path_names) -> str:
    """``tier`` in {"L1","L2","L3"}. *path_names are category display names in order."""
    key = "||".join(str(x) for x in (tier, root_display) + path_names)
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return f"{XML_MOD}.pc_{h}"
