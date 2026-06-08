from contextlib import redirect_stdout
import io

import endpoints
from safety import calculate_safety_stock, get_last_100_outflows


def collect_skus() -> list[str]:
    """Collect SKU input lines until a blank line is entered."""
    print("Enter one SKU per line (e.g. 1-CP-001).")
    print("Press Enter on a blank line to finish.")

    skus: list[str] = []
    while True:
        line = input("SKU: ").strip()
        if not line:
            break
        skus.append(line)

    return skus


def infer_tenant_from_sku(sku: str) -> str | None:
    token = sku.upper()
    if "CP" in token:
        return "CP"
    if "DR" in token:
        return "DR"
    return None


def parse_input_line(line: str) -> tuple[str | None, str]:
    """Allow formats: 'SKU', 'CP SKU', 'CP:SKU', 'CP,SKU'."""
    raw = line.strip()
    upper = raw.upper()

    for sep in (":", ",", " "):
        if sep in raw:
            left, right = raw.split(sep, 1)
            tenant = left.strip().upper()
            sku = right.strip()
            if tenant in {"CP", "DR"} and sku:
                return tenant, sku

    return None, raw


def resolve_tenant_and_product_id(tenant_hint: str | None, sku: str) -> tuple[str, int]:
    """Resolve SKU to product ID, trying likely tenants when needed."""
    tenant_candidates: list[str] = []

    if tenant_hint:
        tenant_candidates.append(tenant_hint)

    inferred = infer_tenant_from_sku(sku)
    if inferred and inferred not in tenant_candidates:
        tenant_candidates.append(inferred)

    for fallback in ("CP", "DR"):
        if fallback not in tenant_candidates:
            tenant_candidates.append(fallback)

    errors_by_tenant: dict[str, str] = {}
    for tenant in tenant_candidates:
        try:
            product_id = endpoints.get_product_id_by_sku(tenant, sku)
            return tenant, product_id
        except Exception as exc:
            errors_by_tenant[tenant] = str(exc)

    not_found_markers = (
        "No product found for SKU",
        "No product ID returned for SKU",
    )
    if errors_by_tenant and all(
        any(marker in message for marker in not_found_markers)
        for message in errors_by_tenant.values()
    ):
        raise RuntimeError(
            f"SKU '{sku}' was not found in CP or DR."
        )

    detail = "; ".join(f"{tenant}: {msg}" for tenant, msg in errors_by_tenant.items())
    raise RuntimeError(f"Unable to resolve SKU '{sku}' in CP/DR tenants. {detail}")


def process_sku(
    raw_entry: str,
    start_date: str,
    end_date: str,
    avg_lead_time_days: float = 1,
    max_lead_time_days: float = 1,
) -> None:
    tenant_hint, sku = parse_input_line(raw_entry)
    tenant, product_id = resolve_tenant_and_product_id(tenant_hint, sku)

    outflow_data = get_last_100_outflows(
        tenant,
        product_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Silence verbose internal prints from calculate_safety_stock.
    with redirect_stdout(io.StringIO()):
        working_day_value = calculate_safety_stock(
            outflow_data,
            formula_mode="working_day",
            avg_lead_time_days=avg_lead_time_days,
            max_lead_time_days=max_lead_time_days,
        )
        complex_value = calculate_safety_stock(
            outflow_data,
            formula_mode="complex",
            avg_lead_time_days=avg_lead_time_days,
            max_lead_time_days=max_lead_time_days,
        )
        robust_complex_value = calculate_safety_stock(
            outflow_data,
            formula_mode="robust_complex",
            avg_lead_time_days=avg_lead_time_days,
            max_lead_time_days=max_lead_time_days,
        )

    print(sku)
    print(f"working_day: {working_day_value}")
    print(f"complex: {complex_value}")
    print(f"robust_complex: {robust_complex_value}")


def main() -> None:
    skus = collect_skus()
    if not skus:
        print("No SKUs entered. Exiting.")
        return

    start_date = input("Enter start date (dd/mm/yyyy) or leave blank for 01/01/2025: ").strip() or "01/01/2025"
    end_date = input("Enter end date (dd/mm/yyyy) or leave blank for 31/08/2025: ").strip() or "31/08/2025"

    for entry in skus:
        try:
            process_sku(entry, start_date, end_date)
        except Exception as exc:
            print(f"{entry}")
            print(f"error: {exc}")


if __name__ == "__main__":
    main()
