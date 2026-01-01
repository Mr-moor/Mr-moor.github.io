# bandwidth_control.py

def can_use_internet(user):
    """Check if the user is within their plan's quota."""
    if not user.plan:
        return False
    return user.data_used < user.plan.data_quota and user.is_active

def get_bandwidth_limits(user):
    """Return download/upload limits (in Mbps) if within quota."""
    if can_use_internet(user):
        return user.plan.download_speed, user.plan.upload_speed
    else:
        # If exceeded quota or inactive, throttle to 0 Mbps
        return 0, 0

def update_data_usage(user, mb_used, db):
    """Increase user's data usage."""
    gb_used = mb_used / 1024  # convert MB → GB
    user.data_used += gb_used
    if user.data_used >= user.plan.data_quota:
        user.is_active = False  # disable internet if quota exceeded
    db.session.commit()
