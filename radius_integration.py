import mysql.connector

def grant_wifi_access(username, password="1234"):
    connection = mysql.connector.connect(
        host="localhost",
        user="radius_user",
        password="your_db_password",
        database="radius"
    )
    cursor = connection.cursor()

    cursor.execute(
        "INSERT INTO radcheck (username, attribute, op, value) VALUES (%s, 'Cleartext-Password', ':=', %s)",
        (username, password)
    )

    connection.commit()
    cursor.close()
    connection.close()
    print(f"✅ Wi-Fi access granted for {username}")

# radius_integration.py
def disable_user_access(phone, connection_type):
    print(f"[RADIUS] Disabled {connection_type} access for {phone}")
    # TODO: Implement actual RADIUS or MikroTik API calls here

def enable_user_access(phone, connection_type):
    print(f"[RADIUS] Enabled {connection_type} access for {phone}")
    # TODO: Implement actual RADIUS or MikroTik API calls here

def apply_bandwidth_limits(username, download_speed, upload_speed):
    """
    Pushes bandwidth limits to RADIUS attributes.
    Example uses Mikrotik attributes.
    """
    from your_database_config import db_connection

    cursor = db_connection.cursor()
    cursor.execute("""
        INSERT INTO radreply (username, attribute, op, value)
        VALUES
        (%s, 'Mikrotik-Rate-Limit', ':=', %s)
        ON DUPLICATE KEY UPDATE value=%s
    """, (
        username,
        f"{int(download_speed*1024)}/{int(upload_speed*1024)}",  # Kbps
        f"{int(download_speed*1024)}/{int(upload_speed*1024)}"
    ))
    db_connection.commit()
    cursor.close()