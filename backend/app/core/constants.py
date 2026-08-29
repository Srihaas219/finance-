"""Stable role identifiers used for RBAC across the app."""

ROLE_OPERATOR = "data_operator"
ROLE_REVIEWER = "reviewer"
ROLE_CONSUMER = "data_consumer"

ALL_ROLES = frozenset({ROLE_OPERATOR, ROLE_REVIEWER, ROLE_CONSUMER})
