import uuid


def new_request_id() -> str:
    return str(uuid.uuid4())


def log_event(req_id: str, actor_id, log_type: str, message: str):
    request_id = req_id or "LOCAL"
    actor = str(actor_id) if actor_id not in (None, "") else "SYSTEM"
    print(f"[{request_id}] [{actor}] {{{log_type}}}: {message}", flush=True)
