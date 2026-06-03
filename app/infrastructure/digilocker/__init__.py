"""DigiLocker API provider module.

Provides interface, mock, stub, and placeholder real implementations.
"""

from app.infrastructure.digilocker.client import RealDigiLockerProvider
from app.infrastructure.digilocker.interface import DigiLockerProvider
from app.infrastructure.digilocker.mock import MockDigiLockerProvider
from app.infrastructure.digilocker.stub import StubDigiLockerProvider

__all__ = [
    "DigiLockerProvider",
    "RealDigiLockerProvider",
    "MockDigiLockerProvider",
    "StubDigiLockerProvider",
]
