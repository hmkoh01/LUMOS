"""Productization interfaces for future cloud/account work.

These types are intentionally not wired into the local MVP runtime yet.
"""

from src.product.account import AuthUser, UserAccount
from src.product.auth_service import MockAuthService
from src.product.auth_state import AuthSession, AuthState, AuthStatus
from src.product.cloud_client import CloudAuthClient, CloudClient, CloudClientError, DevCloudAuthClient, MockCloudClient
from src.product.device import MockDeviceRegistry, RegisteredDevice
from src.product.entitlement_cache import EntitlementCacheStatus, EntitlementSnapshot, InMemoryEntitlementCache, OfflineGraceDecision
from src.product.entitlements import EntitlementService, MockEntitlementService, PlanEntitlement, StaticEntitlementService
from src.product.feature_gates import FeatureGateContext, FeatureKey, GateDecision, GateSeverity, StaticFeatureGateService
from src.product.token_store import (
    InMemoryTokenStore,
    KeyringTokenStore,
    TokenBundle,
    TokenStoreBackend,
    TokenStoreError,
    TokenStoreUnavailable,
    build_secure_token_store,
)

__all__ = [
    "CloudClient",
    "CloudAuthClient",
    "CloudClientError",
    "DevCloudAuthClient",
    "EntitlementService",
    "EntitlementCacheStatus",
    "EntitlementSnapshot",
    "FeatureGateContext",
    "FeatureKey",
    "GateDecision",
    "GateSeverity",
    "AuthSession",
    "AuthState",
    "AuthStatus",
    "AuthUser",
    "MockAuthService",
    "MockCloudClient",
    "MockDeviceRegistry",
    "MockEntitlementService",
    "InMemoryEntitlementCache",
    "OfflineGraceDecision",
    "PlanEntitlement",
    "RegisteredDevice",
    "StaticEntitlementService",
    "StaticFeatureGateService",
    "InMemoryTokenStore",
    "KeyringTokenStore",
    "TokenBundle",
    "TokenStoreBackend",
    "TokenStoreError",
    "TokenStoreUnavailable",
    "UserAccount",
    "build_secure_token_store",
]
