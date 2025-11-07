import datetime

def make_event(event_type, camera_id, status="active", **meta):
    """統一事件格式封裝"""
    return {
        "type": event_type,
        "camera_id": camera_id,
        "timestamp": datetime.datetime.now().isoformat(),
        "status": status,
        "meta": meta
    }
