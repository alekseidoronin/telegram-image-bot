import logging
import json
import hmac
import hashlib
import requests
import urllib.parse
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class NowPaymentsGateway:
    """
    Python implementation of NOWPayments (Crypto) integration.
    """
    def __init__(self, api_key: str, ipn_secret: str):
        """
        :param api_key: Your API key from NOWPayments settings
        :param ipn_secret: Secret key for IPN callback validation
        """
        self.api_key = api_key
        self.ipn_secret = ipn_secret
        self.api_url = 'https://api.nowpayments.io/v1/invoice'

    def create_invoice(self, 
                       order_id: str, 
                       amount: float, 
                       currency: str = 'rub', 
                       description: str = 'Оплата заказа', 
                       success_url: str = '', 
                       cancel_url: str = '', 
                       callback_url: str = '') -> Optional[str]:
        """
        Create a crypto invoice and return the payment URL.
        """
        payload = {
            'price_amount': amount,
            'price_currency': currency,
            'order_id': order_id,
            'order_description': description,
        }
        if success_url: payload['success_url'] = success_url
        if cancel_url: payload['cancel_url'] = cancel_url
        if callback_url: payload['ipn_callback_url'] = callback_url

        logger.info(f"NOWPayments Payload: {payload}")

        headers = {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json',
        }

        try:
            logger.info(f"Creating NOWPayments invoice for order {order_id}, amount {amount} {currency}")
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=15)
            data = response.json()
            
            if 200 <= response.status_code < 300 and data.get('invoice_url'):
                return data['invoice_url']
            else:
                logger.error(f"NOWPayments error: Status {response.status_code}, Response: {data}")
        except Exception as e:
            logger.error(f"NOWPayments exception: {e}")

        return None

    def validate_callback(self, payload_json: str, signature_header: str) -> bool:
        """
        Validate incoming IPN webhook from NOWPayments.
        """
        try:
            data = json.loads(payload_json)
            if not data:
                return False

            # Sort keys alphabetically 
            sorted_keys = sorted(data.keys())
            sorted_data = {k: data[k] for k in sorted_keys}
            
            # NOWPayments uses JSON without escaping unicode characters
            sorted_json = json.dumps(sorted_data, separators=(',', ':'), ensure_ascii=False)
            
            # Generate HMAC SHA-512
            computed = hmac.new(
                self.ipn_secret.encode('utf-8'),
                sorted_json.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()

            return hmac.compare_digest(computed, signature_header)
        except Exception:
            return False


class YooMoneyGateway:
    """
    Python implementation of YooMoney (QuickPay) integration.
    """
    def __init__(self, receiver_wallet: str, secret_key: str, success_url: str = ''):
        """
        :param receiver_wallet: YooMoney wallet number (receiver)
        :param secret_key: Secret key from notification settings
        :param success_url: Redirect URL after successful payment
        """
        self.receiver_wallet = receiver_wallet
        self.secret_key = secret_key
        self.success_url = success_url

    def generate_payment_url(self, order_id: str, amount: float, description: str = 'Оплата заказа') -> str:
        """
        Generate payment URL for YooMoney QuickPay.
        """
        params = {
            'receiver': self.receiver_wallet,
            'quickpay-form': 'button',
            'targets': description,
            'paymentType': 'AC',  # 'AC' - bank card, 'PC' - YooMoney wallet
            'sum': amount,
            'formcomment': "Оплата заказа",
            'short-dest': "Оплата заказа",
            'label': order_id,
            'successURL': self.success_url,
        }

        query_string = urllib.parse.urlencode(params)
        return f"https://yoomoney.ru/quickpay/confirm.xml?{query_string}"

    def validate_callback(self, post_data: Dict[str, str]) -> bool:
        """
        Validate incoming HTTP notification from YooMoney.
        """
        try:
            fields = [
                post_data.get('notification_type', ''),
                post_data.get('operation_id', ''),
                post_data.get('amount', ''),
                post_data.get('currency', ''),
                post_data.get('datetime', ''),
                post_data.get('sender', ''),
                post_data.get('codepro', ''),
                self.secret_key,
                post_data.get('label', ''),
            ]

            check_string = '&'.join(map(str, fields))
            sha1_hash = post_data.get('sha1_hash', '')
            
            computed = hashlib.sha1(check_string.encode('utf-8')).hexdigest()
            
            return hmac.compare_digest(computed, sha1_hash)
        except Exception:
            return False
