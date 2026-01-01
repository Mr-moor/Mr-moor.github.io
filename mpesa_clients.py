# mpesa_clients.py
import os
import requests
import base64
from requests.auth import HTTPBasicAuth
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class MpesaClient:
    def __init__(self):
        self.consumer_key = "q8XQWxRqiqzr6HPsOPiFghU0gkRTSil8t0AVLA07C7N7HUMj"
        self.consumer_secret = "6cVFJcgLdxtPQ6MSpGPyYElC1ngjmGdbRYAd0QcIvDrEkxKk2mZ871KHcSsPfBiH"
        self.shortcode = "174379"  # ✅ removed tuple mistake
        self.passkey = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
        self.base_url = os.getenv("MPESA_BASE_URL", "https://sandbox.safaricom.co.ke")
        self.callback_url = os.getenv("CALLBACK_URL")  # ✅ Matches your .env key

    def get_access_token(self):
        """Generate an access token from Safaricom API."""
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        resp = requests.get(url, auth=HTTPBasicAuth(self.consumer_key, self.consumer_secret), timeout=10)
        resp.raise_for_status()
        return resp.json().get("access_token")

    def stk_push(self, phone_number, amount_kes, transaction_id):
        """Initiate an STK push request."""
        token = self.get_access_token()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password_str = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(password_str.encode()).decode()

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount_kes),
            "PartyA": phone_number,
            "PartyB": self.shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": self.callback_url,
            "AccountReference": f"SUB{transaction_id}",
            "TransactionDesc": "WiFi Purchase"
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            f"{self.base_url}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers=headers,
            timeout=10
        )

        print("DEBUG M-PESA RESPONSE:", response.text)
        response.raise_for_status()
        return response.json()
