"""Verification orchestration service.

Coordinates the end-to-end DigiLocker verification flow by delegating
to the OAuth, token, and repository layers.
"""


class VerificationService:
    """Orchestrates the DigiLocker verification flow.

    Responsibilities:
        - Initiate a new verification (create record, build auth URL)
        - Handle the OAuth callback (exchange code, validate token)
        - Expose verification status to callers
    """

    pass
