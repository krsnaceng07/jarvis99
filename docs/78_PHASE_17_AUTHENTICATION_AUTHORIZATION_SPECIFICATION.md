# 78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 17: Authentication, Authorization & API Security**. It secures the API Gateway (Phase 14) and Persistent Execution layer (Phase 15) by introducing JWT Bearer and API Key authentication services, a fine-grained role-and-permission-based access control (RBAC/PBAC) model, request-identity context propagation, token revocation, rate limiting, and security telemetry auditing.

## Status
**STATUS:** FROZEN (v1.0: 2026-06-30, 288 passed; v1.1 per CR-001 on 2026-07-10)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phases 1–16
**Freeze Date:** 2026-06-30 (v1.1: 2026-07-10)
**Approved by:** Architecture Gatekeeper after full quality gate verification.

---

## 1. Architectural Position

The security layer resides at the perimeter of the API Gateway, intercepting incoming HTTP and WebSocket requests, validating client identity credentials, and injecting a thread-safe / context-local identity struct.

```
       Client Request (HTTP Headers / WS Sub-Protocol)
                             │
                             ▼
     FastAPI Security Middlewares / Auth Middleware
         ├── RateLimitMiddleware (Sensitive routes, e.g. login)
         ├── AuthenticationMiddleware
         │     ├── JWT Verification (Bearer JWT Header / WS Handshake)
         │     └── API Key Validation (X-API-Key Header)
         │
         ▼
         RequestContext Injector (ContextVar Context)
                             │
                             ▼
     Role/Permission Dependency Guard (Depends(require_permissions(...)))
                             │
                             ▼
         Target API Router (Agent, Workflow, Audit)
```

---

## 2. Scope & Boundaries

### In Scope
- **Dedicated Authentication Services**: Layered security modules under `core/security/` isolating encryption, JWT signing, password checks, configuration loading, and context holding from database repositories.
- **Hashed Refresh Tokens**: Session keys are stored in the database as salted cryptographically secure SHA-256 hashes.
- **Explicit JWT Claims**: Strict parsing of standardized claims (`sub`, `username`, `roles`, `permissions`, `iat`, `exp`, `jti`, `iss`, `aud`).
- **Permission-Based RBAC/PBAC**: Roles are modeled as collections of explicit permission scopes. Direct user-permission mapping is supported to allow user-specific overrides.
- **Unified Request Context**: ContextVar propagating client user profile metadata down the service call stack.
- **Access Control & Telemetry Auditing**: Denying unauthorized execution and broadcasting security audit events via EventBus (`user.login`, `authorization.denied`, etc.).
- **Separate Rate Limiting Middleware**: Intercepts requests before authentication to apply rate limits.
- **Configuration Service**: Centralized injection provider for secrets (JWT secret, issuer, audience, bcrypt cost).

### Out of Scope (Non-Goals)
- ❌ Third-party OAuth2 redirects (Google/GitHub/Okta).
- ❌ Multi-Factor Authentication (MFA).
- ❌ Local filesystem permission virtualization.

---

## 2.1 Architecture Invariants
In order to enforce strict code-base separation, the following architectural invariants are permanently active:
- **✓ SecurityRepository performs CRUD only.** No business rules or auth token logic is allowed.
- **✓ PasswordService never accesses the database.**
- **✓ JWTService performs cryptographic operations only.** It does not access database files or repositories.
- **✓ RevocationService performs token revocation checks.** Keeps database lookup decoupled from token validation logic.
- **✓ AuthenticationService coordinates all authentication flows.** Acts as the single coordinator.
- **✓ Authorization decisions occur exclusively through `require_permissions()` dependency guards.**
- **✓ RequestContext is immutable after authentication.** Once parsed, context properties cannot be modified.
- **✓ API routers never inspect JWT claims directly.** Routers inspect only the injected `RequestContext`.
- **✓ Repositories never parse JWTs.**
- **✓ Authentication failures always fail closed.** Malformed tokens, DB timeouts, or expired payloads default to 401/403.
- **✓ Secrets are obtained exclusively from ConfigurationService.** No environment variables are accessed directly outside ConfigurationService.
- **✓ Constant-time comparison is required for API key verification.** Timing attacks are blocked.
- **✓ Refresh tokens are rotated on every successful refresh.** Old refresh tokens are invalidated immediately.
- **✓ No core module imports `api/`.** Strict API-layer to core-layer dependency direction is preserved.

---

## 3. Database Schema Specifications

The new schemas are registered on the shared SQLAlchemy metadata baseline (`Base` class in `core/memory/models.py`).

### 3.1 Users Table (`users`)
Stores user accounts, passwords, and status flags.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Uuid` | Primary Key | User ID |
| `username` | `String(255)` | Unique, Not Null | Unique username |
| `email` | `String(255)` | Unique, Not Null | Unique email address |
| `hashed_password` | `String(255)` | Not Null | Hashed password |
| `is_active` | `Boolean` | Not Null, Default True | Active account status flag |
| `tenant_id` | `Uuid` | Nullable | Reserved for future multi-tenancy |
| `failed_login_count` | `Integer` | Not Null, Default 0 | Counter for failed attempts |
| `locked_until` | `DateTime` | Nullable | Lock timeout for lockout policy |
| `password_changed_at`| `DateTime` | Nullable | Timestamp of last password modification |
| `last_login` | `DateTime` | Nullable | Timestamp of last successful login |
| `created_at` | `DateTime` | Not Null, Default UTC | Registration timestamp |
| `updated_at` | `DateTime` | Not Null, Default UTC | Last updated timestamp |

### 3.2 Roles Table (`roles`)
Stores role definitions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | Primary Key | Role ID |
| `name` | `String(100)` | Unique, Not Null | Role name (e.g. `admin`, `developer`, `viewer`) |

### 3.3 Permissions Table (`permissions`)
Stores discrete permission scopes.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | Primary Key | Permission ID |
| `scope` | `String(100)` | Unique, Not Null | Permission scope (e.g. `workflow.read`) |

### 3.4 Role Permissions Association Table (`role_permissions`)
Maps roles to their assigned permission scopes.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `role_id` | `Integer` | FK (roles.id), PK | Reference to role |
| `permission_id` | `Integer` | FK (permissions.id), PK | Reference to permission |

### 3.5 User Roles Table (`user_roles`)
Maps users to their assigned roles.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `user_id` | `Uuid` | FK (users.id), PK | Reference to user |
| `role_id` | `Integer` | FK (roles.id), PK | Reference to role |

### 3.6 User Direct Permissions Table (`user_permissions`)
Enables direct user-permission overrides bypassing roles.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `user_id` | `Uuid` | FK (users.id), PK | Reference to user |
| `permission_id` | `Integer` | FK (permissions.id), PK | Reference to permission |

### 3.7 API Keys Table (`api_keys`)
Stores user programmatic access tokens.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Uuid` | Primary Key | API Key record ID |
| `user_id` | `Uuid` | FK (users.id), Not Null | Owner of this API key |
| `name` | `String(100)` | Not Null | User-assigned key name |
| `prefix` | `String(16)` | Not Null | Display prefix (e.g. `jvs_live_`) |
| `hashed_key` | `String(255)` | Not Null, Unique | Salted SHA-256 hash of key |
| `is_active` | `Boolean` | Not Null, Default True | Active status flag |
| `expires_at` | `DateTime` | Nullable | Expiration date |
| `created_at` | `DateTime` | Not Null, Default UTC | Creation timestamp |

### 3.8 Refresh Tokens Table (`refresh_tokens`)
Tracks active refresh tokens using SHA-256 hashes.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Uuid` | Primary Key | Token ID |
| `user_id` | `Uuid` | FK (users.id), Not Null | Reference to user |
| `token_hash` | `String(255)` | Unique, Not Null | Salted SHA-256 hash of refresh token |
| `is_revoked` | `Boolean` | Not Null, Default False | Revoked flag |
| `expires_at` | `DateTime` | Not Null | Expiration timestamp |
| `created_at` | `DateTime` | Not Null, Default UTC | Issuance timestamp |

### 3.9 Token Blacklist Table (`revoked_tokens`)
Tracks blacklisted JWT identifiers (`jti`) until expiry.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, Autoincrement | Record index |
| `jti` | `String(255)` | Unique, Not Null | Blacklisted JWT ID |
| `expires_at` | `DateTime` | Not Null | Expiration timestamp |

---

## 4. Component Boundaries & Core Security Services

Security features are strictly isolated inside `core/security/` separating business operations from database layers:
1. **`core/security/configuration_service.py`**: Reads secrets and configurations (JWT Secret, Bcrypt cost, default variables).
2. **`core/security/password_service.py`**: Handles password hashing (`bcrypt` cost >= 12) and password verification.
3. **`core/security/jwt_service.py`**: Signs and decodes JWT tokens, verifying claims structures.
4. **`core/security/revocation_service.py`**: Manages access token blacklist checks based on `jti`.
5. **`core/security/api_key_service.py`**: Generates keys and validates API Key payloads using constant-time comparisons.
6. **`core/security/auth_context.py`**: Thread-safe ContextVar holder for the current `RequestContext`.
7. **`core/security/rbac_service.py`**: Resolves permissions (combining role-inherited and user-direct permissions) and matches scopes.
8. **`core/security/auth_service.py`**: Coordinates login, refresh (invalidating old and returning new refresh tokens), and logout actions.
9. **`core/security/seed_service.py`**: Seeds default roles/permissions. Development seed administrator accounts are provisioned *only* if `ENVIRONMENT=development`, loading the username and password dynamically from configuration environment variables.

### Standardized Request Context
```python
class RequestContext(BaseModel):
    user_id: UUID
    username: str
    roles: list[str]
    permissions: list[str]
    authentication_method: Literal["jwt", "api_key"]
    request_id: Optional[UUID] = None
```

---

## 5. API Gateway Interface & Middleware Changes

### Rate Limiting & Auth Middleware Separation
1. **`RateLimitMiddleware`**: Runs first, checking endpoint limits (e.g. 5 attempts/minute for `/auth/login`) without inspecting database credentials.
2. **`AuthenticationMiddleware`**: Intercepts requests after rate limits have passed, resolving authentication headers and injecting the resulting `RequestContext`.

### REST Endpoints
- `POST /api/v1/auth/login` (Unprotected)
  - Validate username/password, generate raw access JWT and refresh token, store SHA-256 hashes, return raw values.
- `POST /api/v1/auth/refresh` (Unprotected)
  - Validate SHA-256 hash of refresh token, invalidate old refresh token, generate new access + refresh token pair, return raw values.
- `POST /api/v1/auth/logout` (Protected)
  - Revokes refresh token and blacklists access JWT `jti` in database.
- `GET /api/v1/users/me` (Protected)
  - Returns requesting profile metadata.

### WebSocket Authentication (`/ws/v1/telemetry`)
WebSockets authenticate **during HTTP Handshake only**, validating the token subprotocol or query parameter, binding the resulting `RequestContext`, and preserving it without repeated parses.

---

## 6. Verification, Telemetry Auditing & Acceptance Criteria

### Security Audit Events (EventBus Telemetry)
Broadcaster publishes telemetry events to EventBus upon key lifecycles:
- `user.login`
- `user.logout`
- `user.auth_failed`
- `user.auth_denied`
- `apikey.created`
- `apikey.revoked`

---

## 7. Suggested Milestone Breakdown

| Milestone | Component | Description |
|-----------|-----------|-------------|
| **Milestone 0** | Security ORM models | Set up ORM schemas (`UserModel`, `RoleModel`, `PermissionModel`, `ApiKeyModel`, `RefreshTokenModel`, `RevokedTokenModel`). |
| **Milestone 1** | SecurityRepository | Implement CRUD data handlers for security tables (`core/tools/security_repository.py`). |
| **Milestone 2** | PasswordService | Implement secure password hashing and verification (`core/security/password_service.py`). |
| **Milestone 3** | JWTService & RevocationService | Implement JWT signing/decoding and token revocation blacklist lookup. |
| **Milestone 4** | APIKeyService | Implement constant-time key parsing and validation. |
| **Milestone 5** | AuthenticationService & SeedService | Coordinate login, token rotation, and seed defaults based on development configurations. |
| **Milestone 6** | RequestContext & Middlewares | Implement context holder, RateLimitMiddleware, and AuthenticationMiddleware. |
| **Milestone 7** | RBAC/PBAC Dependency Guards | Implement `require_permissions` guards verifying roles and direct user permissions. |
| **Milestone 8** | Authentication Routes | Implement `/login`, `/refresh`, `/logout`, and `/users/me` API routing. |
| **Milestone 9** | Protect Existing Routes | Restrict API Gateway endpoints, handle WS handshake auth, and wire EventBus security telemetry logs. |
| **Milestone 10**| Tests & Quality Gates | Write test suite (100% security coverage), Ruff/Mypy validation, and Freeze documents. |

---

## 8. Acceptance Criteria (Freeze Gate)

| Gate | Tool / Command | Result at Freeze |
|------|----------------|------------------|
| Format | `ruff format --check` | PASS |
| Lint | `ruff check` | PASS |
| Types | `mypy api core audit` | PASS |
| Tests | `pytest tests/` | **288 passed**, 0 regression |
| Coverage | `pytest --cov=core --cov=api` | **93%** (≥80% target) |
| Architecture audit | `python -m audit.cli` | PASS |
| Authority audit | `python -m audit.cli` | PASS |
| Security tests | `tests/test_api_security.py` | 22 passed |

---

## Change Control Log

| CR | Date | Summary | Scope | Approved by |
|----|------|---------|-------|-------------|
| CR-017-001 | 2026-06-30 | Gateway lifespan calls `kernel.boot()` so security services register at startup; SQLite dev schema auto-materialization; `JarvisError` re-raise in `db_manager.session()` preserves 401 auth failures; agent/workflow routes protected via `require_permissions`; auth + users routers mounted | `api/main.py`, `api/routes/*`, `core/kernel.py`, `core/memory/database.py` | Architect (Rank 0) |
| CR-001 | 2026-07-10 | Add `skill.read` to the default permission scope seed in `core/security/seed_service.py`. Required by the Phase 41 Capability Registry which guards `/api/v1/discover` (and any future read-gated skill routes) with `_require_read = require_permissions(["skill.read"])`. Admin role inherits the new scope automatically on next boot. Existing tokens issued before this change must be re-issued to obtain the new permission claim. | `core/security/seed_service.py` | Architect (Rank 0) |

---

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [26_SECURITY_CONSTITUTION.md](file:///e:/jarvis/docs/26_SECURITY_CONSTITUTION.md)
- [27_PERMISSION_SYSTEM.md](file:///e:/jarvis/docs/27_PERMISSION_SYSTEM.md)
- [60_MASTER_INDEX.md](file:///e:/jarvis/docs/60_MASTER_INDEX.md)
