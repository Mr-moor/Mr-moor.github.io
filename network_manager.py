import requests
from flask import current_app
from datetime import datetime

# Example RouterOS (MikroTik) API endpoint and credentials
MIKROTIK_API = "http://192.168.88.1/rest"
MIKROTIK_USER = "Admin"
MIKROTIK_PASS = "password"

def mikrotik_api_call(endpoint, data=None, method='GET'):
    """Generic REST API call to Mikrotik RouterOS"""
    url = f"{MIKROTIK_API}/{endpoint.strip('/')}"
    auth = (MIKROTIK_USER, MIKROTIK_PASS)
    if method == 'GET':
        r = requests.get(url, auth=auth, timeout=10)
    elif method == 'POST':
        r = requests.post(url, json=data, auth=auth, timeout=10)
    elif method == 'DELETE':
        r = requests.delete(url, auth=auth, timeout=10)
    else:
        raise ValueError("Unsupported method")
    r.raise_for_status()
    return r.json() if r.text else {}

# -------------------------------
# PPPoE MANAGEMENT
# -------------------------------
def create_pppoe_user(username, password, download_limit, upload_limit):
    """Create PPPoE user with bandwidth limits"""
    payload = {
        "name": username,
        "password": password,
        "profile": "default",
        "service": "pppoe",
        "comment": f"Created {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "limit-bytes-in": download_limit,
        "limit-bytes-out": upload_limit
    }
    return mikrotik_api_call("/ppp/secret/add", payload, method='POST')

def remove_pppoe_user(username):
    """Remove PPPoE user"""
    users = mikrotik_api_call("/ppp/secret/print", method='GET')
    for user in users:
        if user['name'] == username:
            mikrotik_api_call(f"/ppp/secret/remove?=.id={user['.id']}", method='DELETE')
            return True
    return False

# -------------------------------
# HOTSPOT MANAGEMENT
# -------------------------------
def create_hotspot_user(username, password, time_limit=None, data_limit=None):
    """Create a hotspot user (voucher or phone-based)"""
    payload = {
        "name": username,
        "password": password,
        "server": "hotspot1",
        "profile": "default",
        "comment": f"Hotspot user created {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    }
    if time_limit:
        payload["limit-uptime"] = time_limit
    if data_limit:
        payload["limit-bytes-total"] = data_limit
    return mikrotik_api_call("/ip/hotspot/user/add", payload, method='POST')

def remove_hotspot_user(username):
    """Delete hotspot user"""
    users = mikrotik_api_call("/ip/hotspot/user/print", method='GET')
    for user in users:
        if user['name'] == username:
            mikrotik_api_call(f"/ip/hotspot/user/remove?=.id={user['.id']}", method='DELETE')
            return True
    return False

# -------------------------------
# STATIC IP MANAGEMENT
# -------------------------------
def assign_static_ip(mac_address, ip_address, comment=""):
    """Reserve a static IP for a specific MAC address"""
    payload = {
        "mac-address": mac_address,
        "address": ip_address,
        "comment": comment or f"Static IP for {mac_address}"
    }
    return mikrotik_api_call("/ip/dhcp-server/lease/add", payload, method='POST')

def remove_static_ip(mac_address):
    """Remove a static IP reservation"""
    leases = mikrotik_api_call("/ip/dhcp-server/lease/print", method='GET')
    for lease in leases:
        if lease['mac-address'] == mac_address:
            mikrotik_api_call(f"/ip/dhcp-server/lease/remove?=.id={lease['.id']}", method='DELETE')
            return True
    return False
