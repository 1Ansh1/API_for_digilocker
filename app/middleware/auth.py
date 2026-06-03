"""JWT authentication middleware.

Validates bearer tokens on protected endpoints and populates
``request.state.user_id`` for downstream handlers.

To be implemented in Phase 2.
"""
