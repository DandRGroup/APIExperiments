import requests
import json
from typing import Dict, Any
from auth import get_access_token, invalidate_token, WG_BASE

def get_stock_movements(tenant: str, product_id: int, skip_count: int = 0) -> Dict[str, Any]:
    """
    Fetch stock movements for a product from WorkGuru API.
    
    Args:
        tenant: The tenant code (e.g., "CP", "DR")
        product_id: The ProductId to fetch movements for
        skip_count: Number of records to skip for paging
        
    Returns:
        The JSON response from the API
        
    Raises:
        RuntimeError: If the API call fails
    """

    # print (f"\n========== FETCHING STOCK MOVEMENTS ==========")
    
    # Get the access token for this tenant
    access_token = get_access_token(tenant)
    
    # Build the API URL
    base = WG_BASE.rstrip("/")
    url = f"{base}/api/services/app/Stock/GetStockMovements"
    
    # Set up headers with the access token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    # Set up request parameters
    params = {
        "ProductId": product_id,
        "MaxResultCount": 100,
        "SkipCount": skip_count,
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()

        items = data.get("result", {}).get("items", [])
        '''
        print(f"Returned {len(items)} item(s)")
        for item in items:
            print(
                f"date={item.get('date')} | "
                f"quantity={item.get('quantity')} | "
                f"direction={item.get('direction')}"
            )
        '''

        return data
        
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            # print(f"[auth] 401 Unauthorized — invalidating token for {tenant} and retrying once...")
            invalidate_token(tenant)
            return get_stock_movements(tenant, product_id, skip_count=skip_count)
        # print(f"\n!!!!!! ERROR FETCHING STOCK MOVEMENTS !!!!!!")
        # print(f"Tenant: {tenant}")
        # print(f"ProductId: {product_id}")
        # print(f"Exception: {repr(e)}")
        raise RuntimeError(
            f"Failed to fetch stock movements from WorkGuru. "
            f"Tenant: {tenant}, ProductId: {product_id}. "
            f"HTTP status: {response.status_code}."
        ) from e
    except requests.exceptions.RequestException as e:
        # print(f"\n!!!!!! ERROR FETCHING STOCK MOVEMENTS !!!!!!")
        # print(f"Tenant: {tenant}")
        # print(f"ProductId: {product_id}")
        # print(f"Exception: {repr(e)}")
        raise RuntimeError(
            f"Failed to fetch stock movements from WorkGuru. "
            f"Tenant: {tenant}, ProductId: {product_id}. "
            f"HTTP status: {getattr(response, 'status_code', 'unknown')}."
        ) from e
    

    

def get_current_stock_levels(tenant: str, product_ids: list) -> Dict[str, Any]:
    """
    Fetch current stock levels for a list of product IDs from WorkGuru API.

    Args:
        tenant: The tenant code (e.g., "CP", "DR")
        product_ids: List of ProductIds to fetch stock levels for

    Returns:
        The JSON response from the API

    Raises:
        RuntimeError: If the API call fails
    """

    # print(f"\n========== FETCHING CURRENT STOCK LEVELS ==========")

    access_token = get_access_token(tenant)

    base = WG_BASE.rstrip("/")
    url = f"{base}/api/services/app/Stock/GetCurrentStockLevelsByListProductIds"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Build repeated query params: ?productIds=x&productIds=y&...
    params = [("productIds", pid) for pid in product_ids]

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        items = response.json().get("result", [])
        return {
            item["productId"]: [
                level["quantity"]
                for level in item.get("warehouseLevels", [])
            ]
            for item in items
        }

    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            # print(f"[auth] 401 Unauthorized — invalidating token for {tenant} and retrying once...")
            invalidate_token(tenant)
            return get_current_stock_levels(tenant, product_ids)
        # print(f"\n!!!!!! ERROR FETCHING CURRENT STOCK LEVELS !!!!!!")
        # print(f"Tenant: {tenant}")
        # print(f"ProductIds: {product_ids}")
        # print(f"Exception: {repr(e)}")
        raise RuntimeError(
            f"Failed to fetch current stock levels from WorkGuru. "
            f"Tenant: {tenant}, ProductIds: {product_ids}. "
            f"HTTP status: {response.status_code}."
        ) from e
    except requests.exceptions.RequestException as e:
        # print(f"\n!!!!!! ERROR FETCHING CURRENT STOCK LEVELS !!!!!!")
        # print(f"Tenant: {tenant}")
        # print(f"ProductIds: {product_ids}")
        # print(f"Exception: {repr(e)}")
        raise RuntimeError(
            f"Failed to fetch current stock levels from WorkGuru. "
            f"Tenant: {tenant}, ProductIds: {product_ids}. "
            f"HTTP status: {getattr(response, 'status_code', 'unknown')}."
        ) from e


def get_product_id_by_sku(tenant: str, sku: str, _retried: bool = False) -> int:
    """
    Fetch a product by SKU and return its product ID.

    Args:
        tenant: The tenant code (e.g., "CP", "DR")
        sku: The product SKU (e.g., "1-CP-001")
        _retried: Internal flag to prevent infinite 401 retries

    Returns:
        The product ID for the SKU

    Raises:
        RuntimeError: If the API call fails or response has no product ID
    """

    # print(f"\n========== FETCHING PRODUCT ID BY SKU ==========")

    access_token = get_access_token(tenant)

    base = WG_BASE.rstrip("/")
    url = f"{base}/api/services/app/Product/GetProductBySku"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    params = {
        "sku": sku,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result")

        # API may return result=None when SKU does not exist.
        if not isinstance(result, dict):
            raise RuntimeError(
                f"No product found for SKU '{sku}' (tenant: {tenant})."
            )

        product_id = result.get("id")

        if product_id is None:
            raise RuntimeError(
                f"No product ID returned for SKU '{sku}' (tenant: {tenant})."
            )

        return product_id

    except requests.exceptions.HTTPError as e:
        if response.status_code == 401 and not _retried:
            # print(f"[auth] 401 Unauthorized - invalidating token for {tenant} and retrying once...")
            invalidate_token(tenant)
            return get_product_id_by_sku(tenant, sku, _retried=True)
        # print(f"\n!!!!!! ERROR FETCHING PRODUCT BY SKU !!!!!!")
        # print(f"Tenant: {tenant}")
        # print(f"SKU: {sku}")
        # print(f"Exception: {repr(e)}")
        raise RuntimeError(
            f"Failed to fetch product by SKU from WorkGuru. "
            f"Tenant: {tenant}, SKU: {sku}. "
            f"HTTP status: {response.status_code}."
        ) from e
    except requests.exceptions.RequestException as e:
        # print(f"\n!!!!!! ERROR FETCHING PRODUCT BY SKU !!!!!!")
        # print(f"Tenant: {tenant}")
        # print(f"SKU: {sku}")
        # print(f"Exception: {repr(e)}")
        raise RuntimeError(
            f"Failed to fetch product by SKU from WorkGuru. "
            f"Tenant: {tenant}, SKU: {sku}. "
            f"HTTP status: {getattr(response, 'status_code', 'unknown')}."
        ) from e


if __name__ == "__main__":
    # Example usage
    tenant_code = "CP"  # or "DR"
    product_id = 873085  # replace with actual ProductId
    stock_data = get_stock_movements(tenant_code, product_id)
    # print(json.dumps(stock_data, indent=2))
