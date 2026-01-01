from routeros_api import RouterOsApiPool

def allow_user_on_mikrotik(ip="192.168.88.1", username="Admin", password="1234", user_phone="254712345678"):
    pool = RouterOsApiPool(ip, username=username, password=password, plaintext_login=True)
    api = pool.get_api()

    # Add user to hotspot
    api.get_resource('/ip/hotspot/user').add(
        name=user_phone,
        password='wifi123',
        profile='default'
    )

    print(f"✅ Mikrotik user {user_phone} added successfully.")
    pool.disconnect()
