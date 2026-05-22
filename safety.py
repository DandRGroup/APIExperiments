from collections import defaultdict
from datetime import datetime, timedelta
import math

import endpoints

# Registry of named products with their tenant-specific product IDs.
# Use 0 (or None) if the product does not exist in a given tenant.
PRODUCTS: dict[str, dict[str, int]] = {
    "bow_shackle_12mm_ss316": {"CP": 873388, "DR": 0},
    "bow_shackle_10mm_ss316": {"CP": 873389, "DR": 0},
    "47mmWebbing": {"CP": 2152651, "DR": 1879550},
}

def _percentile(sorted_values: list[float], p: float) -> float:
    """Return percentile using linear interpolation (p in [0, 100])."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    rank = (len(sorted_values) - 1) * (p / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(sorted_values[low])
    weight = rank - low
    return float(sorted_values[low] * (1 - weight) + sorted_values[high] * weight)


def _parse_movement_datetime(raw_date: str) -> datetime:
    return datetime.strptime(raw_date, "%d/%m/%Y %H:%M")

def calculate_safety_stock(
    out_movements: list[dict],
    formula_mode: str = "working_day",
    avg_lead_time_days: float = 2,
    max_lead_time_days: float = 10,
) -> int:
    """
    Calculate a simple safety stock value from Out movements.

    Expected input shape:
    [
        {
            "date": "01/05/2026 07:02",
            "quantity": 5.0,
            "direction": "Out",
        }
    ]

    Formula modes:
    - working_day:
        minimum_safety_stock = average_usage_per_working_day * 22
    - complex:
        safety_stock = (max_daily_usage * max_lead_time_days) - (average_usage_per_working_day * avg_lead_time_days)
    - robust_complex:
        safety_stock = (robust_max_daily_usage * max_lead_time_days) - (average_usage_per_working_day * avg_lead_time_days)

    Rules:
    - Only movements with direction == "Out" are treated as demand
    - Quantities are grouped by calendar day
    - Working days are Monday-Friday across the observed period
    - Result is rounded up to the nearest whole number
    - Minimum return value is 0
    """

    if not out_movements:
        return 0

    daily_out_usage = defaultdict(float)

    for item in out_movements:
        quantity = float(item.get("quantity", 0) or 0)
        if quantity <= 0:
            continue

        raw_date = item.get("date")
        if not raw_date:
            continue

        # Expected format from your sample: "01/05/2026 07:02"
        day = datetime.strptime(raw_date, "%d/%m/%Y %H:%M").date()
        daily_out_usage[day] += quantity

    if not daily_out_usage:
        return 0

    daily_totals = list(daily_out_usage.values())
    all_dates = sorted(daily_out_usage.keys())
    period_days = (all_dates[-1] - all_dates[0]).days + 1
    total_quantity = sum(daily_totals)

    print(f"\n[safety stock] --- Per-movement breakdown ---")
    for d in all_dates:
        print(f"[safety stock]   {d}: {daily_out_usage[d]:.2f}")

    sorted_totals = sorted(daily_totals)
    avg_daily_usage = sum(daily_totals) / len(daily_totals)
    avg_daily_usage_over_period = total_quantity / period_days
    max_daily_usage = max(daily_totals)
    min_daily_usage = min(daily_totals)
    median_daily_usage = _percentile(sorted_totals, 50)

    trim_percent = 15
    robust_low = _percentile(sorted_totals, trim_percent)
    robust_high = _percentile(sorted_totals, 100 - trim_percent)
    non_outlier_totals = [x for x in daily_totals if robust_low <= x <= robust_high]
    outlier_count = len(daily_totals) - len(non_outlier_totals)

    robust_source = non_outlier_totals if non_outlier_totals else daily_totals
    robust_avg_daily_usage = sum(robust_source) / len(robust_source)
    robust_max_daily_usage = max(robust_source)
    robust_median_daily_usage = _percentile(sorted(robust_source), 50)

    working_days = 0
    current_day = all_dates[0]
    while current_day <= all_dates[-1]:
        if current_day.weekday() < 5:
            working_days += 1
        current_day += timedelta(days=1)

    if working_days == 0:
        return 0

    avg_usage_per_working_day = total_quantity / working_days
    minimum_safety_stock = avg_usage_per_working_day * 22

    print(f"\n--- Variable snapshot ---")
    print(f"Formula mode selected: {formula_mode}")
    print(f"Period: {all_dates[0]} to {all_dates[-1]} ({period_days} calendar days)")
    print(f"Total quantity out: {total_quantity:.2f}")
    print(f"Active days with usage: {len(daily_totals)}")
    print(f"Working days in period: {working_days}")
    print(f"Min daily usage: {min_daily_usage:.2f}")
    print(f"Median daily usage: {median_daily_usage:.2f}")
    print(f"Max daily usage: {max_daily_usage:.2f}")
    print(f"Avg daily usage (active days only): {avg_daily_usage:.2f}")
    print(f"Avg daily usage (over full period):  {avg_daily_usage_over_period:.2f}")
    print(f"Avg usage per working day: {avg_usage_per_working_day:.2f}")
    print(f"Robust trim percent each side: {trim_percent}%")
    print(f"Robust trim bounds: [{robust_low:.2f}, {robust_high:.2f}]")
    print(f"Outlier days removed for robust mode: {outlier_count}")
    print(f"Robust avg daily usage: {robust_avg_daily_usage:.2f}")
    print(f"Robust median daily usage: {robust_median_daily_usage:.2f}")
    print(f"Robust max daily usage: {robust_max_daily_usage:.2f}")

    #complex formula with or without outlier trimming

    print(
        f"Formula (complex): "
        f"({max_daily_usage:.2f} * {max_lead_time_days}) - ({avg_usage_per_working_day:.2f} * {avg_lead_time_days})"
    )
    complex_min = (max_daily_usage * max_lead_time_days) - (
        avg_usage_per_working_day * avg_lead_time_days
    )

    print (f"complex: {complex_min}")

    # robust complex formula that trims outliers from the max daily usage input

    robust_min = (robust_max_daily_usage * max_lead_time_days) - (
        avg_usage_per_working_day * avg_lead_time_days
    )

    print (f"robust_complex: {robust_min}")

    # working day formula

    working_min = avg_usage_per_working_day * 22
        
    print(f"working_day: {working_min}")
    working_min = minimum_safety_stock


    if formula_mode == "complex":
        safety_stock = complex_min
    elif formula_mode == "robust_complex":
        safety_stock = robust_min
    else:
        safety_stock = working_min

    print(f"[Raw result: {safety_stock:.2f} -> ceiled to {max(0, math.ceil(safety_stock))}]")

    return max(0, math.ceil(safety_stock))

def get_last_100_outflows(
    tenant: str,
    product_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Fetch stock movements in pages and keep the latest 100 Out records only."""
    outflows: list[dict] = []
    skip_count = 0
    start_dt = datetime.strptime(start_date, "%d/%m/%Y") if start_date else None
    end_dt = datetime.strptime(end_date, "%d/%m/%Y") if end_date else None

    while len(outflows) < 100:
        payload = endpoints.get_stock_movements(tenant, product_id, skip_count=skip_count)
        items = payload.get("result", {}).get("items", [])
        if not items:
            break

        for item in items:
            if str(item.get("direction", "")).strip().lower() != "out":
                continue

            raw_date = item.get("date")
            if not raw_date:
                continue

            movement_dt = _parse_movement_datetime(raw_date)
            if start_dt and movement_dt < start_dt:
                continue
            if end_dt and movement_dt >= end_dt + timedelta(days=1):
                continue

            outflows.append(
                {
                    "date": raw_date,
                    "quantity": item.get("quantity"),
                    "direction": item.get("direction"),
                }
            )

            if len(outflows) >= 100:
                break

        skip_count += 100

    outflows.sort(key=lambda item: _parse_movement_datetime(item["date"]), reverse=True)

    #print(f"[safety stock] Collected {len(outflows)} Out movement(s) for calculation")
    return outflows[:100]

def get_stock_levels_multi_tenant(tenant_products: list[tuple[str, int]]) -> dict:
    """
    Fetch current stock levels across multiple tenants.

    Args:
        tenant_products: list of (tenant, product_id) tuples
                         e.g. [("CP", 873389), ("CP", 873388), ("DR", 12345)]

    Returns:
        Merged dict of {productId: [primary_qty, secondary_qty, ...]}
    """
    grouped = defaultdict(list)
    for tenant, product_id in tenant_products:
        grouped[tenant].append(product_id)

    result = {}
    for tenant, product_ids in grouped.items():
        levels = endpoints.get_current_stock_levels(tenant, product_ids)
        result.update(levels)
    return result


def get_stock_by_name(*names: str) -> dict:
    """
    Fetch current stock levels for named products across all their tenants.

    Args:
        *names: One or more keys from the PRODUCTS registry.

    Returns:
        {name: {tenant: [warehouse_qtys]}}
    """
    # Build (tenant, product_id) pairs, skipping missing IDs
    pairs: list[tuple[str, int]] = []
    for name in names:
        for tenant, product_id in PRODUCTS[name].items():
            if product_id:
                pairs.append((tenant, product_id))

    # Reverse lookup: product_id -> (name, tenant)
    id_to_meta: dict[int, tuple[str, str]] = {}
    for name in names:
        for tenant, product_id in PRODUCTS[name].items():
            if product_id:
                id_to_meta[product_id] = (name, tenant)

    flat = get_stock_levels_multi_tenant(pairs)

    result: dict[str, dict[str, list]] = {name: {} for name in names}
    for product_id, levels in flat.items():
        name, tenant = id_to_meta[product_id]
        result[name][tenant] = levels
    return result



def flows():
    # Fetch and stitch last 100 Out movements from paged API results

    tenant = input("Enter tenant (e.g. CP): ").strip()

    code = input("Enter product code (e.g. 873389): ").strip()

    start_date = input("Enter start date (dd/mm/yyyy) or leave blank for 01/01/2025: ").strip()
    end_date = input("Enter end date (dd/mm/yyyy) or leave blank for 31/08/2025: ").strip()

    outflow_data = get_last_100_outflows(
        tenant,
        int(code),
        start_date=start_date if start_date else "01/01/2025",
        end_date=end_date if end_date else "31/08/2025",
    )
    print ("--- Sample output of fetched Out movements ---")

    for item in outflow_data[:20]:  # Print first 5 for brevity
        print(f"{item['date']} | Quantity: {item['quantity']} | Direction: {item['direction']}")

    

    # Choose formula_mode: "working_day" or "complex"
    minimum_stock = calculate_safety_stock(
        outflow_data,
        formula_mode="working_day",
        avg_lead_time_days=1,
        max_lead_time_days=1,
    )

    print(f"Calculated Safety Stock: {minimum_stock}")
    


if __name__ == "__main__":

    # Fetch and stitch last 100 Out movements from paged API results
    
    #data = endpoints.get_current_stock_levels("CP", [873389, 873388])

    flows()
