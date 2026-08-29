import uuid


def new_id() -> str:
    """Opaque unique id for entities (uuid4 hex)."""
    return uuid.uuid4().hex
