"""
Timezone utility for Pakistan Standard Time (PST / Asia/Karachi = UTC+5).
Provides a drop-in replacement for datetime.utcnow() that returns the current
Pakistan local time as a timezone-naive datetime (compatible with SQLite/SQLAlchemy).
"""
from datetime import datetime, timezone, timedelta

PKT = timezone(timedelta(hours=5))  # Pakistan Standard Time (UTC+5)

def now_pkt() -> datetime:
    """Return current Pakistan time as a naive datetime (strips tzinfo for DB compatibility)."""
    return datetime.now(PKT).replace(tzinfo=None)
