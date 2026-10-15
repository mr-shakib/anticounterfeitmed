"""Catalog functions other apps may call."""

from __future__ import annotations

from apps.catalog.models import PRODUCT_INFORMATION_FIELDS, Product


def product_information_entries(product: Product) -> list[dict[str, str]]:
    """A product's information as an ordered list of ``{field, text}``.

    A list rather than an object, because canonical JSON sorts object keys and
    the order is part of how the information reads.
    """
    stored = product.information or {}
    return [
        {"field": field, "text": stored[field]}
        for field in PRODUCT_INFORMATION_FIELDS
        if isinstance(stored.get(field), str) and stored[field].strip()
    ]
