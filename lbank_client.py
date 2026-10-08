"""
LBank API Client — EXBT/USDT Market Maker Bot
Supports REST API v2 with HmacSHA256 signature
"""

import hmac
import hashlib
import time
import uuid
import requests
import logging
from urllib.parse import urlencode
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lbkex.com"


class LBankAPIError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"LBank API Error {code}: {message}")


class LBankClient:
    def __init__(self, api_key: str, secret_key: str, use_rsa: bool = False):
        self.api_key = api_key
        self.secret_key = secret_key
        self.use_rsa = use_rsa
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "EXBT-MM-Bot/1.0"
        })

    # ─── Signature ──────────────────────────────────────────────────────────

    def _sign(self, params: dict) -> str:
        """HmacSHA256 signature — LBank v2 style"""
        sorted_params = sorted(params.items())
        query_string = urlencode(sorted_params)
        # MD5 of query string first (LBank requirement)
        md5_hash = hashlib.md5(query_string.encode()).hexdigest().upper()
        # Then HmacSHA256
        signature = hmac.new(
            self.secret_key.encode(),
            md5_hash.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _build_params(self, extra: dict) -> dict:
        if self.use_rsa:
            raise NotImplementedError("RSA signing is not implemented; use an HmacSHA256 API key.")
        params = {
            "api_key":   self.api_key,
            "signature_method": "HmacSHA256",
            "timestamp": str(int(time.time() * 1000)),
            "echostr":   uuid.uuid4().hex,
        }
        params.update(extra)
        params["sign"] = self._sign(params)
        return params

    # ─── Raw HTTP ───────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict = None) -> dict:
        url = BASE_URL + path
        for attempt in range(1, 4):
            try:
                resp = self.session.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if str(data.get("result", "true")).lower() == "false":
                    raise LBankAPIError(data.get("error_code", -1), data.get("msg", "Unknown"))
                return data
            except requests.RequestException as e:
                logger.warning(f"⚠️ LBank ticker timeout/error ({path}) — retry {attempt}/3: {e}")
                if attempt == 3:
                    logger.error("⚠️ Fresh price unavailable — trading cycle skipped safely.")
                    raise
                time.sleep(2 * attempt)

    def _post(self, path: str, extra_params: dict) -> dict:
        url = BASE_URL + path
        params = self._build_params(extra_params)
        headers = {name: params.pop(name) for name in
                   ("timestamp", "signature_method", "echostr")}
        try:
            resp = self.session.post(url, data=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if str(data.get("result", "true")).lower() == "false":
                raise LBankAPIError(data.get("error_code", -1), data.get("msg", "Unknown"))
            return data
        except requests.RequestException as e:
            logger.error(f"POST {path} failed: {e}")
            raise

    # ─── Market Data (Public) ────────────────────────────────────────────────

    def get_ticker(self, symbol: str) -> dict:
        """Get current price ticker"""
        data = self._get("/v2/ticker.do", {"symbol": symbol})
        return data["data"][0] if isinstance(data.get("data"), list) else data["data"]

    def get_orderbook(self, symbol: str, size: int = 20) -> dict:
        """Get order book depth"""
        data = self._get("/v2/depth.do", {"symbol": symbol, "size": size})
        return data.get("data", data)

    def get_mid_price(self, symbol: str) -> float:
        """Calculate mid price from order book"""
        ob = self.get_orderbook(symbol, size=5)
        best_bid = float(ob["bids"][0][0])
        best_ask = float(ob["asks"][0][0])
        mid = (best_bid + best_ask) / 2
        logger.debug(f"Mid price: {mid:.8f} | Bid: {best_bid} | Ask: {best_ask}")
        return mid

    def get_last_price(self, symbol: str) -> float:
        """Get last traded price"""
        ticker = self.get_ticker(symbol)
        return float(ticker["ticker"]["latest"])

    # ─── Account (Private) ───────────────────────────────────────────────────

    def get_balances(self) -> dict:
        """Get all account balances (free and freeze)"""
        balances = {"free": {}, "freeze": {}}
        try:
            # LBank often uses supplement/user_info.do for actual spot balances on newer accounts
            data = self._post("/v2/supplement/user_info.do", {})
            assets = data.get("data", [])
            if isinstance(assets, list):
                for item in assets:
                    coin = item.get("coin", "").upper()
                    if coin:
                        balances["free"][coin] = float(item.get("usableAmt", 0.0))
                        balances["freeze"][coin] = float(item.get("freezeAmt", 0.0))
                return balances
        except Exception as e:
            logger.warning(f"Failed to fetch supplement/user_info.do: {e}")
            
        # Fallback to standard user_info.do
        data = self._post("/v2/user_info.do", {})
        info = data.get("info", {})
        for k, v in info.get("free", {}).items():
            if k.upper() not in balances["free"]:
                balances["free"][k.upper()] = float(v)
        for k, v in info.get("freeze", {}).items():
            if k.upper() not in balances["freeze"]:
                balances["freeze"][k.upper()] = float(v)
                
        return balances

    def get_balance(self, asset: str) -> float:
        """Get balance for a specific asset"""
        balances = self.get_balances()
        return balances["free"].get(asset.upper(), 0.0) + balances["freeze"].get(asset.upper(), 0.0)

    # ─── Order Management (Private) ──────────────────────────────────────────

    def place_order(self, symbol: str, side: str, price: float,
                    amount: float, order_type: str = "limit",
                    custom_id: str = None) -> dict:
        """
        Place an order on LBank.

        custom_id is used to identify bot-owned orders across restarts.
        """
        order_type_value = side
        if order_type == "maker":
            order_type_value = f"{side}_maker"

        params = {
            "symbol": symbol,
            "type": order_type_value,
            "price": f"{price:.8f}",
            "amount": f"{amount:.2f}",
        }

        if custom_id:
            params["custom_id"] = custom_id

        endpoint = (
            "/v2/supplement/create_order.do"
            if custom_id or order_type == "maker"
            else "/v2/create_order.do"
        )

        data = self._post(endpoint, params)

        order_id = (
            data.get("data", {}).get("order_id")
            or data.get("order_id")
        )

        if not order_id:
            raise LBankAPIError(
                f"Order placement returned no order_id: {data}"
            )

        logger.info(
            f"✅ Order placed: {side.upper()} {amount:.2f} EXBT "
            f"@ {price:.8f} | ID: {order_id} | custom_id={custom_id}"
        )

        return {
            "order_id": str(order_id),
            "side": side,
            "price": price,
            "amount": amount,
            "custom_id": custom_id,
        }

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel a single order"""
        try:
            self._post("/v2/cancel_order.do", {
                "symbol":   symbol,
                "order_id": order_id
            })
            logger.debug(f"Cancelled order: {order_id}")
            return True
        except LBankAPIError as e:
            logger.warning(f"Cancel failed for {order_id}: {e}")
            return False

    def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all open orders for a symbol. Returns count cancelled."""
        orders = self.get_open_orders(symbol)
        cancelled = 0
        for order in orders:
            if self.cancel_order(symbol, order["order_id"]):
                cancelled += 1
            time.sleep(0.1)  # Rate limit protection
        logger.info(f"Cancelled {cancelled} orders for {symbol}")
        return cancelled

    def get_open_orders(self, symbol: str, page: int = 1, page_size: int = 200) -> list:
        """
        Get ALL open/pending orders for a symbol.

        LBank returns paginated data. Keep fetching pages until the
        returned page contains fewer than page_size orders.

        `page` is retained as the starting page for compatibility.
        """
        all_orders = []
        current_page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))
        max_pages = 100

        try:
            for _ in range(max_pages):
                data = self._post("/v2/orders_info_no_deal.do", {
                    "symbol": symbol,
                    "current_page": str(current_page),
                    "page_length": str(page_size)
                })

                payload = data.get("data", {})

                orders = payload.get("orders")
                if orders is None:
                    orders = payload.get("order_list", [])

                if not isinstance(orders, list):
                    logger.warning(
                        f"Unexpected open-order response schema on page "
                        f"{current_page}: {type(orders).__name__}"
                    )
                    break

                logger.info(
                    f"Open orders page {current_page}: {len(orders)} orders"
                )

                # Normalize bot ownership field.
                # Different LBank responses may expose custom_id/customer_id.
                for order in orders:
                    if isinstance(order, dict):
                        cid = (
                            order.get("custom_id")
                            or order.get("customer_id")
                        )
                        order["custom_id"] = cid

                all_orders.extend(orders)

                # Last page reached.
                if len(orders) < page_size:
                    break

                current_page += 1
            else:
                logger.warning(
                    f"Open-order pagination reached safety limit "
                    f"({max_pages} pages) for {symbol}"
                )

            # Protect callers from duplicate order IDs across pages.
            unique_orders = []
            seen_ids = set()

            for order in all_orders:
                oid = str(order.get("order_id", "") or "")

                if oid and oid in seen_ids:
                    continue

                if oid:
                    seen_ids.add(oid)

                unique_orders.append(order)

            logger.info(
                f"Total open orders for {symbol}: "
                f"{len(unique_orders)} unique orders"
            )

            return unique_orders

        except LBankAPIError as e:
            logger.warning(f"get_open_orders error: {e}")
            raise

    def get_order_status(self, symbol: str, order_id: str) -> dict:
        """Get status of a specific order"""
        data = self._post("/v2/orders_info.do", {
            "symbol":   symbol,
            "order_id": order_id
        })
        return data.get("data", {}).get("order_list", [{}])[0]

    # ─── Utility ─────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Test API connectivity"""
        try:
            data = self._get("/v2/timestamp.do")
            logger.info(f"LBank API connected. Server time: {data.get('data')}")
            return True
        except Exception as e:
            logger.error(f"LBank ping failed: {e}")
            return False
