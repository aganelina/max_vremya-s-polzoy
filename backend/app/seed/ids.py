import uuid

_NAMESPACE = uuid.UUID("6f1c2a4e-2d0b-4c55-9d5e-0b7a7b3f9a10")

DEMO_MAX_USER_ID = 1

def demo_id(key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, key)
