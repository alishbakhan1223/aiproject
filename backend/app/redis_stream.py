"""
Thin wrapper around Redis Streams so each camera worker can push detection
events onto a shared stream, independently of other cameras.
"""
import json
import redis

from app.config import settings

_client = redis.Redis(
    host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True
)


def push_event(event: dict):
    """Push a detection event dict onto the shared Redis stream."""
    _client.xadd(settings.REDIS_STREAM_NAME, {"data": json.dumps(event)})


def read_events(last_id: str = "$", count: int = 10, block_ms: int = 5000):
    """
    Blocking read of new events from the stream, starting after last_id.
    Returns list of (id, event_dict).
    """
    resp = _client.xread(
        {settings.REDIS_STREAM_NAME: last_id}, count=count, block=block_ms
    )
    events = []
    for _, messages in resp:
        for msg_id, fields in messages:
            events.append((msg_id, json.loads(fields["data"])))
    return events
