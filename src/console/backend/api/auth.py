import ipaddress
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
import jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from database import get_db
from models.user import User, UserRole, UserStatus
from auth.jwt import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from auth.dependencies import get_current_user
from api.schemas import TokenResponse, TokenRefreshRequest, UserResponse
from config import settings
from services import m365 as m365_service
from services import oidc as oidc_service
from services.audit_chain_service import create_chained_audit_log

router = APIRouter(prefix="/auth", tags=["Authentication"])

_M365_ALLOWED_NETWORKS_ENV = "M365_ALLOWED_NETWORKS"
_MAX_FAILED_LOGINS = 5
_LOCKOUT_MINUTES = 15


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Normalize a possibly-naive DB datetime to UTC-aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_m365_allowed_ip(ip: str | None) -> bool:
    """Return True if the client IP is within the configured M365 allowed networks.

    When M365_ALLOWED_NETWORKS is not set, all IPs are allowed so that firewall /
    reverse-proxy rules remain the sole enforcement layer (backward-compatible).
    Set M365_ALLOWED_NETWORKS=10.0.0.0/8,192.168.0.0/16 to enforce at the app layer.
    """
    allowed_str = os.environ.get(_M365_ALLOWED_NETWORKS_ENV, "").strip()
    if not allowed_str:
        return False  # production default-deny: an explicit allowlist is required
    if not ip:
        return False
    try:
        if ip == "testclient":
            # Starlette TestClient uses a non-IP host for the client address.
            # Map it to loopback so allowlist-based tests stay deterministic;
            # production requests always carry a real IP.
            client_ip = ipaddress.ip_address("127.0.0.1")
        else:
            client_ip = ipaddress.ip_address(ip)
        for cidr in allowed_str.split(","):
            cidr = cidr.strip()
            if cidr and client_ip in ipaddress.ip_network(cidr, strict=False):
                return True
    except ValueError:
        return False
    return False


def _m365_allowlist_configured() -> bool:
    return bool(os.environ.get(_M365_ALLOWED_NETWORKS_ENV, "").strip())


def _client_ip(request: Request) -> str | None:
    """Return the client IP, honoring X-Forwarded-For only when explicitly trusted."""
    if getattr(settings, "trust_proxy_headers", False):
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",", 1)[0].strip() if forwarded else ""
        if first:
            return first
    return request.client.host if request.client else None


def _password_policy_ok(password: str) -> bool:
    """Password must be 8+ chars and contain at least two character classes."""
    if len(password) < 8:
        return False
    classes = 0
    if any(c.islower() for c in password):
        classes += 1
    if any(c.isupper() for c in password):
        classes += 1
    if any(c.isdigit() for c in password):
        classes += 1
    if any(not c.isalnum() for c in password):
        classes += 1
    return classes >= 2


class M365LoginRequest(BaseModel):
    email: EmailStr


class ProfileUpdateRequest(BaseModel):
    full_name: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


def _log_audit(
    db: Session,
    *,
    action: str,
    user_id: str | None,
    detail: str,
    ip: str | None,
) -> None:
    """Record an authentication event on the tamper-evident hash chain.

    These rows used to be inserted without sequence_number/prev_hash/record_hash,
    so verify_chain skipped them: SSO logins (the main path in production) were
    outside the tamper detection the requirements promise. chain linkage only —
    the caller keeps committing its own transaction.
    """
    create_chained_audit_log(
        db,
        user_id=user_id,
        action=action,
        resource_type="auth",
        detail=detail,
        ip_address=ip,
    )


@router.post("/token", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    db: Session = Depends(get_db),
):
    ip = _client_ip(request) if request is not None else None
    user = db.query(User).filter(User.email == form_data.username).first()
    now = _utc_now()
    locked_until = _aware(user.locked_until) if user else None
    if locked_until is not None and locked_until > now:
        create_chained_audit_log(
            db,
            user_id=user.id,
            action="auth.login_blocked",
            resource_type="auth",
            resource_id=user.id,
            detail="account temporarily locked",
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked",
        )
    if not user or not user.hashed_password:
        create_chained_audit_log(
            db,
            user_id=user.id if user else None,
            action="auth.login_failed",
            resource_type="auth",
            detail=f"user not found or password login disabled: {form_data.username}",
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not verify_password(form_data.password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= _MAX_FAILED_LOGINS:
            user.locked_until = _utc_now() + timedelta(minutes=_LOCKOUT_MINUTES)
            detail = f"account locked after {_MAX_FAILED_LOGINS} failures"
        else:
            detail = f"failed login attempt {user.failed_login_attempts}"
        db.commit()
        create_chained_audit_log(
            db,
            user_id=user.id,
            action="auth.login_failed",
            resource_type="auth",
            resource_id=user.id,
            detail=detail,
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    user.last_login = _utc_now()
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    create_chained_audit_log(
        db,
        user_id=user.id,
        action="auth.login_success",
        resource_type="auth",
        resource_id=user.id,
        detail="password login",
        ip_address=ip,
    )

    token_data = {"sub": user.id, "email": user.email, "role": user.role.value}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: TokenRefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token, expected_type="refresh")

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    token_data = {"sub": user.id, "email": user.email, "role": user.role.value}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    body: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    full_name = body.full_name.strip()
    if not full_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="full_name must not be empty",
        )
    current_user.full_name = full_name
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password login is not enabled for this account",
        )
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if not _password_policy_ok(body.new_password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "New password must be at least 8 characters and contain "
                "at least two of: lowercase, uppercase, digits, symbols"
            ),
        )
    current_user.hashed_password = get_password_hash(body.new_password)
    db.commit()
    create_chained_audit_log(
        db,
        user_id=current_user.id,
        action="auth.password_changed",
        resource_type="auth",
        resource_id=current_user.id,
        detail="password changed by user",
        ip_address=None,
    )


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    body: PasswordResetRequest,
    db: Session = Depends(get_db),
):
    """Request a password reset for an existing active account.

    A single-use token is stored as a SHA-256 hash with a 60-minute expiry.
    Delivery is delegated to the email adapter (TODO) or to an admin reset;
    the token is returned in the response only when DEBUG=true for local
    development and automated tests.
    """
    user = db.query(User).filter(User.email == body.email).first()
    if not user or user.status != "active":
        # Do not reveal whether the address exists.
        return {"message": "If the account exists, a reset link has been prepared"}

    token = secrets.token_urlsafe(32)
    user.password_reset_token_hash = hashlib.sha256(token.encode()).hexdigest()
    user.password_reset_expires_at = _utc_now() + timedelta(hours=1)
    db.commit()
    create_chained_audit_log(
        db,
        user_id=user.id,
        action="auth.password_reset_requested",
        resource_type="auth",
        resource_id=user.id,
        detail="password reset token issued",
        ip_address=None,
    )
    response = {"message": "If the account exists, a reset link has been prepared"}
    if settings.debug:
        response["reset_token"] = token
    return response


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    body: PasswordResetConfirm,
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    user = db.query(User).filter(User.password_reset_token_hash == token_hash).first()
    if not user or not user.password_reset_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token"
        )
    expires_at = user.password_reset_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _utc_now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired",
        )
    if not _password_policy_ok(body.new_password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "New password must be at least 8 characters and contain "
                "at least two of: lowercase, uppercase, digits, symbols"
            ),
        )
    user.hashed_password = get_password_hash(body.new_password)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    create_chained_audit_log(
        db,
        user_id=user.id,
        action="auth.password_reset_confirmed",
        resource_type="auth",
        resource_id=user.id,
        detail="password reset completed",
        ip_address=None,
    )


@router.post("/m365/login", response_model=TokenResponse)
def login_m365(
    body: M365LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Non-interactive M365 login bridge.

    The frontend posts the user's email; backend verifies via MS Graph that
    the email exists in the configured tenant (Client Credentials Flow),
    then issues a CivilPDF-DX JWT. If auto_provision is on and no local
    User row exists, a viewer-role user is created.

    Trust model: this endpoint is intended for **LAN-restricted deployments**
    (see docs/architecture/m365-auth-design.md §3). Spoofing is mitigated by
    network boundary + full audit logging, not by interactive MS sign-in.
    """
    email = body.email.lower()
    ip = _client_ip(request)

    if not _m365_allowlist_configured():
        _log_audit(
            db,
            action="m365_login_failed",
            user_id=None,
            detail="M365_ALLOWED_NETWORKS not configured (default-deny)",
            ip=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "M365_ALLOWED_NETWORKS is not configured; the M365 login "
                "bridge is disabled in public deployments"
            ),
        )

    if not _is_m365_allowed_ip(ip):
        _log_audit(
            db,
            action="m365_login_failed",
            user_id=None,
            detail=f"network_blocked ip={ip} email={email}",
            ip=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="M365 login is not allowed from this network",
        )

    try:
        graph_user = m365_service.lookup_user(db, email)
    except m365_service.M365ConfigError as exc:
        _log_audit(
            db,
            action="m365_login_failed",
            user_id=None,
            detail=f"config_error: {exc} ({email})",
            ip=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except m365_service.M365UserNotFound:
        _log_audit(
            db,
            action="m365_user_not_found",
            user_id=None,
            detail=f"email={email}",
            ip=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="M365 account not found in tenant",
        )
    except m365_service.M365AuthError as exc:
        _log_audit(
            db,
            action="m365_login_failed",
            user_id=None,
            detail=f"auth_error: {exc} ({email})",
            ip=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    if not graph_user.get("account_enabled", True):
        _log_audit(
            db,
            action="m365_login_failed",
            user_id=None,
            detail=f"account_disabled email={email}",
            ip=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="M365 account is disabled",
        )

    entra_id = graph_user.get("id")
    settings_row = m365_service.get_settings_row(db)

    # Resolve by entra_id first (immutable Entra identity), then email as fallback.
    # Prevents mis-binding when a user renames/changes their email in Entra.
    user = None
    if entra_id:
        user = db.query(User).filter(User.entra_id == entra_id).first()
    if user is None:
        user_by_email = db.query(User).filter(User.email == email).first()
        if user_by_email is not None:
            if user_by_email.entra_id and user_by_email.entra_id != entra_id:
                # Conflict: this email row is already claimed by a different Entra identity
                _log_audit(
                    db,
                    action="m365_login_failed",
                    user_id=None,
                    detail=f"identity_conflict email={email} entra_id={entra_id}",
                    ip=ip,
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Local account email is bound to a different M365 identity",
                )
            user = user_by_email

    if user is None:
        if not settings_row.auto_provision:
            _log_audit(
                db,
                action="m365_login_failed",
                user_id=None,
                detail=f"no_local_user_and_auto_provision_off email={email}",
                ip=ip,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No local account for this M365 user",
            )
        try:
            role = UserRole(settings_row.default_role or "viewer")
        except ValueError:
            role = UserRole.VIEWER
        user = User(
            email=email,
            username=email.split("@", 1)[0],
            full_name=graph_user.get("display_name") or email,
            role=role,
            status=UserStatus.ACTIVE,
            entra_id=entra_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _log_audit(
            db,
            action="m365_user_provisioned",
            user_id=user.id,
            detail=f"role={role.value} email={email}",
            ip=ip,
        )
    else:
        if user.status != UserStatus.ACTIVE.value and user.status != UserStatus.ACTIVE:
            _log_audit(
                db,
                action="m365_login_failed",
                user_id=user.id,
                detail=f"local_account_not_active status={user.status}",
                ip=ip,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is not active",
            )
        if entra_id and not user.entra_id:
            user.entra_id = entra_id

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    token_data = {"sub": user.id, "email": user.email, "role": role_value}
    _log_audit(
        db,
        action="m365_login_success",
        user_id=user.id,
        detail=f"email={email}",
        ip=ip,
    )
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.get("/oidc/login")
def oidc_login(request: Request):
    """Start Entra ID / OIDC authorization-code flow with PKCE."""
    if not oidc_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC SSO is not configured",
        )
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    state_payload = {
        "type": "oidc_state",
        "sub": state,
        "verifier": verifier,
        "nonce": nonce,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    state_token = jwt.encode(
        state_payload, settings.secret_key, algorithm=settings.algorithm
    )
    try:
        auth_url = oidc_service.build_authorization_url(state, nonce, verifier)
    except oidc_service.OIDCConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    redirect = RedirectResponse(
        auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
    redirect.set_cookie(
        "civilpdf_oidc_state",
        state_token,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
        max_age=600,
        path="/api/v1/auth/oidc",
    )
    return redirect


@router.get("/oidc/callback")
def oidc_callback(
    code: str = "",
    state: str = "",
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Complete the OIDC flow: validate state, exchange code, provision user."""
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code or state"
        )
    state_token = request.cookies.get("civilpdf_oidc_state") if request else None
    if not state_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing state cookie"
        )
    try:
        payload = decode_token(state_token, expected_type="oidc_state")
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state"
        ) from None
    if payload.get("sub") != state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="State mismatch"
        )

    try:
        tokens = oidc_service.exchange_code(code, payload["verifier"])
        claims = oidc_service.validate_id_token(tokens["id_token"], payload["nonce"])
    except (oidc_service.OIDCExchangeError, oidc_service.OIDCValidationError) as exc:
        _log_audit(
            db,
            action="oidc_login_failed",
            user_id=None,
            detail=f"oidc_error: {exc}",
            ip=request.client.host if request and request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    email = (claims.get("email") or "").lower()
    entra_id = claims.get("sub") or claims.get("oid")
    user = None
    if entra_id:
        user = db.query(User).filter(User.entra_id == entra_id).first()
    if user is None and email:
        user_by_email = db.query(User).filter(User.email == email).first()
        if user_by_email is not None:
            if user_by_email.entra_id and user_by_email.entra_id != entra_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Local account email is bound to a different identity",
                )
            user = user_by_email

    if user is None:
        if not settings.oidc_auto_provision or not email:
            _log_audit(
                db,
                action="oidc_login_failed",
                user_id=None,
                detail=f"no_local_user_and_auto_provision_off email={email}",
                ip=request.client.host if request and request.client else None,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No local account for this identity",
            )
        user = User(
            email=email,
            username=(claims.get("preferred_username") or email.split("@", 1)[0]),
            full_name=claims.get("name") or claims.get("email") or email,
            role=UserRole.VIEWER,
            status=UserStatus.ACTIVE,
            entra_id=entra_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _log_audit(
            db,
            action="oidc_user_provisioned",
            user_id=user.id,
            detail=f"role={user.role.value} email={email}",
            ip=request.client.host if request and request.client else None,
        )
    else:
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is not active",
            )
        if entra_id and not user.entra_id:
            user.entra_id = entra_id
        if not user.full_name and claims.get("name"):
            user.full_name = claims["name"]

    user.last_login = datetime.now(timezone.utc)
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    token_data = {"sub": user.id, "email": user.email, "role": role_value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    _log_audit(
        db,
        action="oidc_login_success",
        user_id=user.id,
        detail=f"email={email}",
        ip=request.client.host if request and request.client else None,
    )

    if settings.frontend_origin:
        fragment = (
            f"#access_token={access_token}&refresh_token={refresh_token}"
            f"&token_type=bearer"
        )
        return RedirectResponse(
            settings.frontend_origin.rstrip("/") + "/login" + fragment
        )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
