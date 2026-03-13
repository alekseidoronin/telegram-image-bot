import argparse
import hashlib
import hmac
import json
import os
from typing import Any, Dict

import requests


def build_signature(payload: Dict[str, Any], ipn_secret: str) -> str:
    """
    Reproduce NOWPayments HMAC-SHA512 signature.
    Sort keys alphabetically, dump JSON with ensure_ascii=False and separators=(',', ':').
    """
    sorted_keys = sorted(payload.keys())
    sorted_data = {k: payload[k] for k in sorted_keys}
    sorted_json = json.dumps(sorted_data, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(
        ipn_secret.encode("utf-8"),
        sorted_json.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Test NOWPayments webhook endpoint.")
    parser.add_argument(
        "--url",
        default=os.getenv("TEST_WEBHOOK_URL", "http://localhost:8080/api/webhooks/nowpayments"),
        help="Webhook URL (default: http://localhost:8080/api/webhooks/nowpayments)",
    )
    parser.add_argument(
        "--secret",
        default=os.getenv("NOWPAYMENTS_IPN_SECRET", ""),
        help="NOWPayments IPN secret (or set NOWPAYMENTS_IPN_SECRET env var)",
    )
    parser.add_argument(
        "--order-id",
        default="test-order-123",
        help="Order ID to send in webhook (must exist in transactions table for full flow).",
    )
    parser.add_argument(
        "--status",
        default="finished",
        choices=["finished", "confirmed", "partially_paid"],
        help="Payment status to emulate.",
    )
    parser.add_argument(
        "--amount",
        type=float,
        default=100.0,
        help="Price amount to send in webhook.",
    )
    parser.add_argument(
        "--currency",
        default="USD",
        help="Price currency to send in webhook.",
    )

    args = parser.parse_args()

    if not args.secret:
        raise SystemExit("NOWPAYMENTS_IPN_SECRET is required (pass --secret or set env).")

    payload = {
        "payment_id": 1,
        "payment_status": args.status,
        "pay_address": "test-address",
        "price_amount": args.amount,
        "price_currency": args.currency,
        "amount_paid": args.amount,
        "pay_currency": args.currency,
        "order_id": args.order_id,
        "order_description": "Test webhook payment",
        "ipn_type": "invoice",
    }

    signature = build_signature(payload, args.secret)

    print(f"Sending webhook to {args.url}")
    print("Payload:", json.dumps(payload, ensure_ascii=False, indent=2))
    print("Signature:", signature)

    resp = requests.post(
        args.url,
        headers={"x-nowpayments-sig": signature, "Content-Type": "application/json"},
        data=json.dumps(payload, ensure_ascii=False),
        timeout=10,
    )

    print("Response status:", resp.status_code)
    print("Response body:", resp.text)


if __name__ == "__main__":
    main()

