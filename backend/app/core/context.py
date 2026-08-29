"""Per-request context propagated to logs (request_id) without threading it through calls."""
import contextvars

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
