from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import argparse
import re
from typing import Any

import endpoints
from s2 import parse_input_line, resolve_tenant_and_product_id


DATE_FORMAT = "%d/%m/%Y %H:%M"
ADJUSTMENT_PATTERN = re.compile(r"\bstock\s*adjustment\b", re.IGNORECASE)


@dataclass
class MonthlyUsageResult:
    tenant: str
    product_id: int
    sku: str | None
    total_movements_scanned: int
    included_movements: int
    excluded_adjustments: int
    monthly_usage: dict[str, float]
    avg_monthly_usage_full_span: float


def _parse_movement_datetime(raw_date: str) -> datetime:
    return datetime.strptime(raw_date, DATE_FORMAT)


def _collect_label_text(item: dict[str, Any]) -> str:
    label_fields = (
        "label",
        "movementLabel",
        "description",
        "reason",
        "reference",
        "sourceDocument",
        "sourceDocumentType",
        "notes",
    )
    parts: list[str] = []
    for field in label_fields:
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    return " ".join(parts)


def _is_stock_adjustment(item: dict[str, Any]) -> bool:
    text = _collect_label_text(item)
    return bool(ADJUSTMENT_PATTERN.search(text))


def _iter_all_movements(tenant: str, product_id: int, page_size: int = 100) -> list[dict[str, Any]]:
    skip_count = 0
    all_items: list[dict[str, Any]] = []

    while True:
        payload = endpoints.get_stock_movements(tenant, product_id, skip_count=skip_count)
        items = payload.get("result", {}).get("items", [])
        if not items:
            break

        all_items.extend(items)
        if len(items) < page_size:
            break

        skip_count += page_size

    return all_items


def estimate_monthly_usage(
    tenant: str,
    product_id: int,
    sku: str | None = None,
) -> MonthlyUsageResult:
    all_items = _iter_all_movements(tenant, product_id)

    monthly_totals = defaultdict(float)
    included_count = 0
    adjustment_count = 0
    included_dates: list[datetime] = []

    for item in all_items:
        direction = str(item.get("direction", "")).strip().lower()
        if direction != "out":
            continue

        if _is_stock_adjustment(item):
            adjustment_count += 1
            continue

        quantity = float(item.get("quantity", 0) or 0)
        if quantity <= 0:
            continue

        raw_date = item.get("date")
        if not raw_date:
            continue

        movement_dt = _parse_movement_datetime(raw_date)
        month_key = movement_dt.strftime("%Y-%m")
        monthly_totals[month_key] += quantity
        included_count += 1
        included_dates.append(movement_dt)

    monthly_usage = dict(sorted(monthly_totals.items(), key=lambda kv: kv[0]))

    avg_monthly_full_span = 0.0
    if included_dates:
        first = min(included_dates)
        last = max(included_dates)
        month_span = (last.year - first.year) * 12 + (last.month - first.month) + 1
        avg_monthly_full_span = sum(monthly_usage.values()) / month_span

    return MonthlyUsageResult(
        tenant=tenant,
        product_id=product_id,
        sku=sku,
        total_movements_scanned=len(all_items),
        included_movements=included_count,
        excluded_adjustments=adjustment_count,
        monthly_usage=monthly_usage,
        avg_monthly_usage_full_span=avg_monthly_full_span,
    )


def _resolve_product(tenant: str | None, sku: str | None, product_id: int | None) -> tuple[str, int, str | None]:
    if sku:
        tenant_hint = tenant
        if tenant_hint is None:
            parsed_tenant, parsed_sku = parse_input_line(sku)
            tenant_hint = parsed_tenant
            sku = parsed_sku
        resolved_tenant, resolved_product_id = resolve_tenant_and_product_id(tenant_hint, sku)
        return resolved_tenant, resolved_product_id, sku

    if tenant and product_id is not None:
        return tenant, product_id, None

    raise RuntimeError("Provide either --sku or both --tenant and --product-id.")


def _print_result(result: MonthlyUsageResult) -> None:
    print(f"Tenant: {result.tenant}")
    print(f"Product ID: {result.product_id}")
    if result.sku:
        print(f"SKU: {result.sku}")
    print(f"Stock movements scanned: {result.total_movements_scanned}")
    print(f"Included Out movements: {result.included_movements}")
    print(f"Excluded stock adjustments: {result.excluded_adjustments}")

    if not result.monthly_usage:
        print("No matching usage movements found.")
        return

    print("\nMonthly usage totals:")
    for month, qty in result.monthly_usage.items():
        print(f"{month}: {qty:.2f}")

    print(f"\nEstimated average monthly usage (full observed month span): {result.avg_monthly_usage_full_span:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate monthly item usage from historical stock movements."
    )
    parser.add_argument("--tenant", choices=["CP", "DR"], help="Tenant code")
    parser.add_argument("--sku", help="SKU value, for example 1-CP-001")
    parser.add_argument("--product-id", type=int, help="Product ID")

    args = parser.parse_args()
    tenant, product_id, sku = _resolve_product(args.tenant, args.sku, args.product_id)
    result = estimate_monthly_usage(tenant=tenant, product_id=product_id, sku=sku)
    _print_result(result)


if __name__ == "__main__":
    main()
