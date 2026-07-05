"""
PHASE: 17
STATUS: TESTING
SPECIFICATION:
    docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt as pyjwt
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.config import Settings
from core.memory.database import db_manager
from core.memory.models import Base
from core.memory.security_models import (
    ApiKeyModel,
    PermissionModel,
    RefreshTokenModel,
    RevokedTokenModel,
    RoleModel,
    UserModel,
)
from core.security.configuration_service import ConfigurationService
from core.security.jwt_service import JWTService
from core.security.password_service import PasswordService
from core.security.revocation_service import RevocationService
from core.tools.security_repository import SecurityRepository


@pytest.mark.asyncio
async def test_security_orm_models_and_relationships() -> None:
    """Verify all security models create properly, map relationships, and handle cascades."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    # Create all tables on metadata
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    # 1. Create a user, a role, and a permission
    user_id = uuid4()
    api_key_id = uuid4()
    refresh_token_id = uuid4()

    async with db_manager.session() as session:
        # Create permissions
        perm1 = PermissionModel(scope="agent.execute")
        perm2 = PermissionModel(scope="workflow.read")
        session.add_all([perm1, perm2])
        await session.flush()

        # Create role and link permissions
        admin_role = RoleModel(name="admin")
        admin_role.permissions.append(perm1)
        admin_role.permissions.append(perm2)
        session.add(admin_role)
        await session.flush()

        # Create user and link roles + direct permissions
        user = UserModel(
            id=user_id,
            username="testadmin",
            email="admin@test.com",
            hashed_password="bcrypt_hashed_string",
            is_active=True,
        )
        user.roles.append(admin_role)
        user.direct_permissions.append(perm2)
        session.add(user)
        await session.flush()

        # Create API key linked to user
        api_key = ApiKeyModel(
            id=api_key_id,
            user_id=user_id,
            name="testkey",
            prefix="jvs_live_",
            hashed_key="sha256_hashed_key_string",
            is_active=True,
        )
        session.add(api_key)

        # Create Refresh token linked to user
        ref_token = RefreshTokenModel(
            id=refresh_token_id,
            user_id=user_id,
            token_hash="sha256_hashed_refresh_token",
            is_revoked=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add(ref_token)

        # Create Revoked Token Blacklist entry
        rev_token = RevokedTokenModel(
            jti="jwt_jti_value",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        session.add(rev_token)

        await session.commit()

    # 2. Query and verify all elements and relationships
    async with db_manager.session() as session:
        # Query User with eager loading
        stmt = (
            select(UserModel)
            .where(UserModel.id == user_id)
            .options(
                selectinload(UserModel.roles).selectinload(RoleModel.permissions),
                selectinload(UserModel.direct_permissions),
                selectinload(UserModel.api_keys),
                selectinload(UserModel.refresh_tokens),
            )
        )
        res = await session.execute(stmt)
        user_record = res.scalar_one_or_none()
        assert user_record is not None
        assert user_record.username == "testadmin"
        assert len(user_record.roles) == 1
        assert user_record.roles[0].name == "admin"
        assert len(user_record.roles[0].permissions) == 2
        assert len(user_record.direct_permissions) == 1
        assert user_record.direct_permissions[0].scope == "workflow.read"

        # Check API keys
        assert len(user_record.api_keys) == 1
        assert user_record.api_keys[0].name == "testkey"
        assert user_record.api_keys[0].prefix == "jvs_live_"

        # Check Refresh tokens
        assert len(user_record.refresh_tokens) == 1
        assert user_record.refresh_tokens[0].token_hash == "sha256_hashed_refresh_token"

        # Query Revoked Token
        stmt_rev = select(RevokedTokenModel).where(
            RevokedTokenModel.jti == "jwt_jti_value"
        )
        res_rev = await session.execute(stmt_rev)
        rev_record = res_rev.scalar_one_or_none()
        assert rev_record is not None
        assert rev_record.jti == "jwt_jti_value"

    # 3. Test cascade deletion of API keys and Refresh tokens when User is deleted
    async with db_manager.session() as session:
        stmt = select(UserModel).where(UserModel.id == user_id)
        res = await session.execute(stmt)
        user_record = res.scalar_one()
        await session.delete(user_record)
        await session.commit()

    async with db_manager.session() as session:
        # Verify API key is deleted
        stmt_key = select(ApiKeyModel).where(ApiKeyModel.id == api_key_id)
        res_key = await session.execute(stmt_key)
        assert res_key.scalar_one_or_none() is None

        # Verify Refresh token is deleted
        stmt_ref = select(RefreshTokenModel).where(
            RefreshTokenModel.id == refresh_token_id
        )
        res_ref = await session.execute(stmt_ref)
        assert res_ref.scalar_one_or_none() is None

    await db_manager.close()


@pytest.mark.asyncio
async def test_security_repository_crud() -> None:
    """Verify all CRUD methods in SecurityRepository."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    repo = SecurityRepository()
    user_id = uuid4()
    api_key_id = uuid4()
    refresh_token_id = uuid4()

    async with db_manager.session() as session:
        # 1. Save permission
        p1 = PermissionModel(scope="workflow.execute")
        p2 = PermissionModel(scope="audit.read")
        await repo.save_permission(p1, session)
        await repo.save_permission(p2, session)

        # 2. Save role
        role = RoleModel(name="developer")
        role.permissions.append(p1)
        await repo.save_role(role, session)

        # 3. Save user
        user = UserModel(
            id=user_id,
            username="devuser",
            email="dev@test.com",
            hashed_password="hashed_pw_here",
            is_active=True,
        )
        user.roles.append(role)
        user.direct_permissions.append(p2)
        await repo.save_user(user, session)

        # 4. Save API Key
        api_key = ApiKeyModel(
            id=api_key_id,
            user_id=user_id,
            name="devkey",
            prefix="jvs_dev_",
            hashed_key="sha256_dev_key",
            is_active=True,
        )
        await repo.save_api_key(api_key, session)

        # 5. Save Refresh Token
        ref = RefreshTokenModel(
            id=refresh_token_id,
            user_id=user_id,
            token_hash="sha256_ref_hash",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        await repo.save_refresh_token(ref, session)

        # 6. Save Revoked Token
        rev1 = RevokedTokenModel(
            jti="revoked_jti_1",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),  # expired
        )
        rev2 = RevokedTokenModel(
            jti="revoked_jti_2",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),  # active
        )
        await repo.save_revoked_token(rev1, session)
        await repo.save_revoked_token(rev2, session)

        await session.commit()

    # Query and verify using repository methods
    async with db_manager.session() as session:
        # User checks
        user_by_id = await repo.get_user_by_id(user_id, session)
        assert user_by_id is not None
        assert user_by_id.username == "devuser"
        assert len(user_by_id.roles) == 1
        assert user_by_id.roles[0].name == "developer"
        assert len(user_by_id.direct_permissions) == 1
        assert user_by_id.direct_permissions[0].scope == "audit.read"

        user_by_name = await repo.get_user_by_username("devuser", session)
        assert user_by_name is not None
        assert user_by_name.id == user_id

        # Role and Permission checks
        role_by_name = await repo.get_role_by_name("developer", session)
        assert role_by_name is not None
        assert len(role_by_name.permissions) == 1
        assert role_by_name.permissions[0].scope == "workflow.execute"

        perm_by_scope = await repo.get_permission_by_scope("audit.read", session)
        assert perm_by_scope is not None

        # API Key checks
        key_by_hash = await repo.get_api_key_by_hashed("sha256_dev_key", session)
        assert key_by_hash is not None
        assert key_by_hash.name == "devkey"
        assert key_by_hash.user.username == "devuser"

        # Refresh Token checks
        ref_by_hash = await repo.get_refresh_token_by_hash("sha256_ref_hash", session)
        assert ref_by_hash is not None
        assert ref_by_hash.id == refresh_token_id

        # Blacklisted JTI checks
        assert await repo.is_jti_revoked("revoked_jti_1", session) is True
        assert await repo.is_jti_revoked("revoked_jti_2", session) is True
        assert await repo.is_jti_revoked("non_existent_jti", session) is False

    # Delete refresh token and clean expired revoked JTIs
    async with db_manager.session() as session:
        ref_by_hash = await repo.get_refresh_token_by_hash("sha256_ref_hash", session)
        assert ref_by_hash is not None
        await repo.delete_refresh_token(ref_by_hash, session)

        cleaned_count = await repo.cleanup_expired_revoked_tokens(session)
        assert cleaned_count > 0
        await session.commit()

    async with db_manager.session() as session:
        # Verify deleted refresh token
        assert await repo.get_refresh_token_by_hash("sha256_ref_hash", session) is None

        # Verify cleaned expired revoked token (rev1 deleted, rev2 remains)
        assert await repo.is_jti_revoked("revoked_jti_1", session) is False
        assert await repo.is_jti_revoked("revoked_jti_2", session) is True

    await db_manager.close()


@pytest.mark.asyncio
async def test_password_service() -> None:
    """Verify PasswordService hashing and verification behaviors."""
    # 1. Initialize password service
    service = PasswordService(cost_factor=12)

    # 2. Hashing identical passwords produces different hashes (salt is randomized)
    pw = "JarvisSecurePassword123!"
    hash1 = service.hash_password(pw)
    hash2 = service.hash_password(pw)
    assert hash1.startswith("$2b$")
    assert hash1 != hash2

    # 3. Verification checks
    assert service.verify_password(pw, hash1) is True
    assert service.verify_password(pw, hash2) is True
    assert service.verify_password("wrong_password", hash1) is False

    # 4. Fail closed on corrupted hashes
    assert service.verify_password(pw, "corrupted_hash_format") is False
    assert service.verify_password(pw, "") is False

    # 5. Cost factor customization
    fast_service = PasswordService(cost_factor=4)
    fast_hash = fast_service.hash_password(pw)
    assert fast_service.verify_password(pw, fast_hash) is True


# ---------------------------------------------------------------------------
# Milestone 3 — JWTService & RevocationService
# ---------------------------------------------------------------------------


def _make_test_config() -> ConfigurationService:
    """Build a deterministic ConfigurationService without touching env vars."""
    config = ConfigurationService()
    config.jwt_secret = "deterministic_test_secret_key_for_jwt_service_tests"
    config.jwt_issuer = "test_issuer"
    config.jwt_audience = "test_audience"
    config.access_token_expire_minutes = 15
    return config


# --- JWTService ----------------------------------------------------------


def test_jwt_service_sign_and_verify_roundtrip() -> None:
    """A freshly signed token decodes successfully with all claims present."""
    config = _make_test_config()
    service = JWTService(config)

    jti = str(uuid4())
    token = service.sign_token(
        user_id="user-123",
        username="alice",
        roles=["admin"],
        permissions=["agent.execute", "workflow.read"],
        jti=jti,
    )

    claims = service.verify_token(token)
    assert claims["sub"] == "user-123"
    assert claims["username"] == "alice"
    assert claims["roles"] == ["admin"]
    assert claims["permissions"] == ["agent.execute", "workflow.read"]
    assert claims["jti"] == jti
    assert claims["iss"] == "test_issuer"
    assert claims["aud"] == "test_audience"
    assert "iat" in claims and "exp" in claims


def test_jwt_service_expired_token_rejected() -> None:
    """An expired token fails verification (fail-closed)."""
    config = _make_test_config()
    service = JWTService(config)

    token = service.sign_token(
        user_id="user-exp",
        username="bob",
        roles=["viewer"],
        permissions=[],
        jti=str(uuid4()),
    )

    # Force expiry by decoding the payload and re-signing with a past expiry.
    payload = service.decode_token_unverified(token)
    past = datetime.now(timezone.utc) - timedelta(minutes=30)
    payload["exp"] = int(past.timestamp())
    expired_token = pyjwt.encode(payload, config.jwt_secret, algorithm="HS256")

    with pytest.raises(pyjwt.PyJWTError):
        service.verify_token(expired_token)


def test_jwt_service_wrong_audience_rejected() -> None:
    """A token with the wrong audience fails verification."""
    config = _make_test_config()
    service = JWTService(config)

    token = service.sign_token(
        user_id="user-aud",
        username="carol",
        roles=["developer"],
        permissions=["workflow.execute"],
        jti=str(uuid4()),
    )

    # Build a verifier expecting a different audience.
    wrong_config = _make_test_config()
    wrong_config.jwt_audience = "different_audience"
    wrong_service = JWTService(wrong_config)

    with pytest.raises(pyjwt.PyJWTError):
        wrong_service.verify_token(token)


def test_jwt_service_tampered_signature_rejected() -> None:
    """A token whose signature was modified fails verification."""
    config = _make_test_config()
    service = JWTService(config)

    token = service.sign_token(
        user_id="user-tamper",
        username="dave",
        roles=["admin"],
        permissions=["agent.execute"],
        jti=str(uuid4()),
    )

    # Flip the first character of the signature segment (avoiding padding bits).
    parts = token.split(".")
    tampered_sig = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    tampered = ".".join([parts[0], parts[1], tampered_sig])

    with pytest.raises(pyjwt.PyJWTError):
        service.verify_token(tampered)


def test_jwt_service_decode_unverified_returns_claims() -> None:
    """decode_token_unverified reads claims without signature validation."""
    config = _make_test_config()
    service = JWTService(config)

    token = service.sign_token(
        user_id="user-decode",
        username="eve",
        roles=["viewer"],
        permissions=["workflow.read"],
        jti="jti-decode-123",
    )

    claims = service.decode_token_unverified(token)
    assert claims["sub"] == "user-decode"
    assert claims["jti"] == "jti-decode-123"


# --- RevocationService ---------------------------------------------------


@pytest.mark.asyncio
async def test_revocation_service_revoke_and_check() -> None:
    """A revoked JTI is reported as revoked after revocation."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    repo = SecurityRepository()
    service = RevocationService(repo)

    jti = "jti-to-revoke"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    async with db_manager.session() as session:
        # Not revoked yet
        assert await service.is_token_revoked(jti, session) is False
        # Revoke it
        await service.revoke_token(jti, expires_at, session)
        await session.commit()
        # Now revoked
        assert await service.is_token_revoked(jti, session) is True

    await db_manager.close()


@pytest.mark.asyncio
async def test_revocation_service_purge_expired() -> None:
    """purge_expired_revocations removes only expired JTI records."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    repo = SecurityRepository()
    service = RevocationService(repo)

    expired_jti = "jti-expired"
    active_jti = "jti-active"
    now = datetime.now(timezone.utc)

    async with db_manager.session() as session:
        await service.revoke_token(expired_jti, now - timedelta(minutes=5), session)
        await service.revoke_token(active_jti, now + timedelta(minutes=15), session)
        await session.commit()

    async with db_manager.session() as session:
        cleaned = await service.purge_expired_revocations(session)
        await session.commit()
        assert cleaned >= 1
        # Expired is gone, active remains
        assert await service.is_token_revoked(expired_jti, session) is False
        assert await service.is_token_revoked(active_jti, session) is True

    await db_manager.close()


# ---------------------------------------------------------------------------
# Milestone 4 — APIKeyService + JWT edge cases
# ---------------------------------------------------------------------------

from core.security.api_key_service import ApiKeyService  # noqa: E402

# --- APIKeyService -------------------------------------------------------


def test_api_key_generation_format_and_entropy() -> None:
    """Generated keys carry the prefix, have sufficient entropy, and are unique."""
    service = ApiKeyService()
    raw, hashed = service.generate_api_key()

    # Prefix present
    assert raw.startswith("jvs_live_")
    # Entropy: 64 hex chars (32 bytes) after the prefix
    entropy = raw[len("jvs_live_") :]
    assert len(entropy) == 64
    assert all(c in "0123456789abcdef" for c in entropy)
    # Hash is a 64-char SHA-256 hex digest
    assert len(hashed) == 64
    # Two generations differ (randomness)
    raw2, _ = service.generate_api_key()
    assert raw2 != raw


def test_api_key_custom_prefix() -> None:
    """A caller-supplied prefix is honored."""
    service = ApiKeyService()
    raw, _ = service.generate_api_key(prefix="jvs_test_")
    assert raw.startswith("jvs_test_")


def test_api_key_verify_success() -> None:
    """A raw key verifies against its own hash."""
    service = ApiKeyService()
    raw, hashed = service.generate_api_key()
    assert service.verify_api_key(raw, hashed) is True


def test_api_key_verify_wrong_key() -> None:
    """A different raw key does not verify against the stored hash."""
    service = ApiKeyService()
    _, hashed = service.generate_api_key()
    other_raw, _ = service.generate_api_key()
    assert service.verify_api_key(other_raw, hashed) is False


def test_api_key_verify_malformed_hash_fails_closed() -> None:
    """Verification fails closed for a corrupted/malformed stored hash."""
    service = ApiKeyService()
    raw, _ = service.generate_api_key()
    assert service.verify_api_key(raw, "not_a_real_hash") is False
    assert service.verify_api_key(raw, "") is False


def test_api_key_hash_is_not_plaintext() -> None:
    """The stored hash must not contain the raw key in any reversible form."""
    service = ApiKeyService()
    raw, hashed = service.generate_api_key()
    # The hash is a SHA-256 digest; the raw key must not appear inside it
    assert raw not in hashed
    # And the hash must not be the raw key itself
    assert hashed != raw


# --- JWT additional edge cases (per architect hardening suggestions) -----


def test_jwt_alg_none_rejected() -> None:
    """A token forged with alg=none is rejected (no algorithm downgrade)."""
    import base64
    import json

    config = _make_test_config()
    service = JWTService(config)

    # Build a legitimate token, then forge an alg=none variant.
    real = service.sign_token(
        user_id="user-alg",
        username="f",
        roles=["viewer"],
        permissions=[],
        jti=str(uuid4()),
    )
    header_b64, payload_b64, _ = real.split(".")

    # Forge header {"alg":"none","typ":"JWT"} without padding
    forged_header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()
    ).rstrip(b"=")
    forged_token = f"{forged_header.decode()}.{payload_b64}."

    with pytest.raises(pyjwt.PyJWTError):
        service.verify_token(forged_token)


def test_jwt_wrong_secret_rejected() -> None:
    """A token signed with a different secret fails verification."""
    config = _make_test_config()
    service = JWTService(config)

    token = service.sign_token(
        user_id="user-secret",
        username="g",
        roles=["viewer"],
        permissions=[],
        jti=str(uuid4()),
    )

    wrong_config = _make_test_config()
    wrong_config.jwt_secret = "a_completely_different_secret_at_least_32bytes"
    wrong_service = JWTService(wrong_config)

    with pytest.raises(pyjwt.PyJWTError):
        wrong_service.verify_token(token)


def test_jwt_missing_claims_decode_still_structured() -> None:
    """decode_token_unverified returns the payload even if claims are sparse.

    This documents that the unverified decode does NOT enforce required claims;
    downstream consumers must check `sub`/`jti`/`exp` themselves.
    """

    config = _make_test_config()
    # Hand-build a token missing several required claims, signed correctly.
    now = datetime.now(timezone.utc)
    sparse_payload = {
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
    }
    token = pyjwt.encode(sparse_payload, config.jwt_secret, algorithm="HS256")

    # Unverified decode does not raise for missing claims...
    service = JWTService(config)
    claims = service.decode_token_unverified(token)
    assert "sub" not in claims
    assert "jti" not in claims

    # ...but full verify enforces iss/aud (configured), so it rejects.
    with pytest.raises(pyjwt.PyJWTError):
        service.verify_token(token)


# ---------------------------------------------------------------------------
# Milestone 9–10 — Gateway integration (auth routes + protected endpoints)
# ---------------------------------------------------------------------------


def test_agent_run_requires_authentication() -> None:
    """POST /agent/run returns 401 when no credentials are supplied."""
    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/run", json={"goal": "Unauthorized attempt"}
        )
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "AUTH_005"


def test_users_me_returns_profile(auth_headers: dict[str, str]) -> None:
    """GET /users/me returns the authenticated profile from RequestContext."""
    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/users/me", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["username"] == "integration-test-user"
    assert "agent.execute" in body["data"]["permissions"]
    assert body["data"]["authentication_method"] == "jwt"


def test_auth_login_route_registered() -> None:
    """Auth router is mounted under /api/v1/auth/login."""
    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "nobody", "password": "wrong"},
        )
    # Invalid credentials still prove the route exists (not 404).
    assert response.status_code in (401, 403)
