import time
import logging
from typing import List, Optional, Set
from pydantic import BaseModel, Field
import jwt
from jwt import PyJWKClient, InvalidTokenError
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

security_bearer = HTTPBearer(auto_error=False)

# Standard Enterprise Roles
ROLE_EMPLOYEE = "employee"
ROLE_IT_SUPPORT = "it_support"
ROLE_ADMIN = "admin"

# Role hierarchy: higher roles implicitly contain lower permissions
ROLE_HIERARCHY = {
    ROLE_ADMIN: {ROLE_ADMIN, ROLE_IT_SUPPORT, ROLE_EMPLOYEE},
    ROLE_IT_SUPPORT: {ROLE_IT_SUPPORT, ROLE_EMPLOYEE},
    ROLE_EMPLOYEE: {ROLE_EMPLOYEE},
}


class UserContext(BaseModel):
    user_id: str
    username: str
    email: str = ""
    roles: List[str] = Field(default_factory=lambda: [ROLE_EMPLOYEE])
    department: str = "General"
    auth_provider: str = "Keycloak"

    def has_role(self, required_role: str) -> bool:
        user_roles_lower = {r.lower().replace("role_", "") for r in self.roles}
        required_lower = required_role.lower().replace("role_", "")
        
        # Check direct role or hierarchy
        for r in user_roles_lower:
            if r in ROLE_HIERARCHY and required_lower in ROLE_HIERARCHY[r]:
                return True
            if r == required_lower:
                return True
        return False

    def has_any_role(self, required_roles: List[str]) -> bool:
        return any(self.has_role(role) for role in required_roles)


_jwks_client: Optional[PyJWKClient] = None

def get_keycloak_jwks_client() -> Optional[PyJWKClient]:
    global _jwks_client
    if _jwks_client is None and settings.keycloak_enabled:
        jwks_url = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
        try:
            _jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=3600)
            logger.info("Keycloak JWKS client initialized: %s", jwks_url)
        except Exception as e:
            logger.warning("Could not initialize Keycloak JWKS client: %s", e)
    return _jwks_client


def create_demo_jwt(
    username: str = "employee.demo",
    roles: Optional[List[str]] = None,
    email: str = "employee@novaretail.com",
    department: str = "Retail Operations",
    expires_in_hours: int = 24
) -> str:
    """Creates a signed JWT token for dev/testing with role claims matching Keycloak's format."""
    roles = roles or [ROLE_EMPLOYEE]
    now = int(time.time())
    payload = {
        "sub": f"usr-{username}",
        "preferred_username": username,
        "email": email,
        "department": department,
        "iss": f"{settings.keycloak_url}/realms/{settings.keycloak_realm}",
        "aud": settings.keycloak_client_id,
        "iat": now,
        "exp": now + (expires_in_hours * 3600),
        "realm_access": {
            "roles": roles
        },
        "resource_access": {
            settings.keycloak_client_id: {
                "roles": roles
            }
        }
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_and_validate_token(token: str) -> UserContext:
    """
    Validates token either through Keycloak RS256 JWKS or dev secret fallback.
    """
    token = token.strip()
    
    # 1. Try Keycloak JWKS verification if Keycloak is enabled
    if settings.keycloak_enabled:
        jwks_client = get_keycloak_jwks_client()
        if jwks_client:
            try:
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                expected_issuer = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    issuer=expected_issuer,
                    options={"verify_aud": False}  # Audiences can vary by client scope
                )
                return _build_user_from_payload(payload, "Keycloak-OIDC")
            except Exception as e:
                logger.debug("Keycloak verification failed, trying dev fallback: %s", e)

    # 2. Development / Demo verification using HS256
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": True, "verify_aud": False}
        )
        return _build_user_from_payload(payload, "Dev-Keycloak-Token")
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _build_user_from_payload(payload: dict, provider: str) -> UserContext:
    roles: Set[str] = set()
    
    # Realm roles
    realm_access = payload.get("realm_access", {})
    if isinstance(realm_access, dict):
        for r in realm_access.get("roles", []):
            roles.add(str(r).lower())
            
    # Resource / Client roles
    resource_access = payload.get("resource_access", {})
    if isinstance(resource_access, dict):
        client_access = resource_access.get(settings.keycloak_client_id, {})
        for r in client_access.get("roles", []):
            roles.add(str(r).lower())
            
    # Direct roles field if present
    if "roles" in payload and isinstance(payload["roles"], list):
        for r in payload["roles"]:
            roles.add(str(r).lower())

    # Fallback to employee if no recognized role
    if not roles:
        roles.add(ROLE_EMPLOYEE)

    return UserContext(
        user_id=payload.get("sub", "usr-anonymous"),
        username=payload.get("preferred_username") or payload.get("username") or payload.get("sub", "user"),
        email=payload.get("email", ""),
        roles=list(roles),
        department=payload.get("department", "Corporate"),
        auth_provider=provider
    )


def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)
) -> UserContext:
    """
    FastAPI dependency to authenticate the request.
    Extracts Bearer token. If omitted and dev_auth_bypass is enabled, returns default Employee.
    """
    if auth and auth.credentials:
        return decode_and_validate_token(auth.credentials)
    
    # Fallback for dev / demonstration mode when no auth header is provided
    if settings.dev_auth_bypass:
        return UserContext(
            user_id="usr-dev-employee",
            username="dev.employee",
            email="dev.employee@novaretail.com",
            roles=[ROLE_EMPLOYEE],
            department="Operations",
            auth_provider="Dev-Default"
        )
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please provide a valid Keycloak Bearer token.",
        headers={"WWW-Authenticate": "Bearer"}
    )


def require_roles(allowed_roles: List[str]):
    """
    FastAPI RBAC dependency factory.
    Enforces that the current authenticated user possesses at least one of the allowed roles.
    """
    def role_checker(user: UserContext = Depends(get_current_user)) -> UserContext:
        if not user.has_any_role(allowed_roles):
            logger.warning(
                "Access denied for user %s (%s). Required roles: %s, User roles: %s",
                user.username, user.user_id, allowed_roles, user.roles
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Access Denied: Insufficient Permissions (RBAC)",
                    "required_roles": allowed_roles,
                    "your_roles": user.roles,
                    "user": user.username,
                }
            )
        return user
    return role_checker

