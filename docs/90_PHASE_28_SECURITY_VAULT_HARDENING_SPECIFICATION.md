# 90_PHASE_28_SECURITY_VAULT_HARDENING_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 28: Security & Vault Hardening**. It upgrades the system's local credentials vault to use cryptographically secure AES-256-GCM encryption, hashes metadata keys to prevent credential discovery, persists the encrypted vault to disk, resolves vault references (`vault://`) inside settings, and secures telemetry WebSocket streams and observability API routes using the existing JWT and API Key authentication systems.

## Status
**STATUS:** FROZEN (2026-07-04) | 1068 passed
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phases 1–27

---

## 1. Architectural Position

Phase 28 hardens the security perimeter at both the persistence (Vault) and routing (API Gateway) boundaries:

```
      Client Request (HTTP/WS)
                 │
                 ▼
         FastAPI Routing
      ┌──────────────────────────────────────────────────────────┐
      │  /api/v1/observability/*  →  require_permissions("audit.read")
      │  /ws/v1/telemetry/stream  →  Handshake Query Auth (JWT/API-Key)
      └───────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
                            Kernel Boot
      ┌──────────────────────────────────────────────────────────┐
      │  Resolve settings placeholders: vault://secret_name      │
      │  Resolves from VaultManager and injects into config      │
      └───────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
                         Local Security Vault
      ┌──────────────────────────────────────────────────────────┐
      │  VaultManager (AES-256-GCM + SHA-256 Hashed Keys)        │
      │  Read/Write to secrets/vault.enc (JSON)                  │
      └──────────────────────────────────────────────────────────┘
```

The vault and authentication updates are integrated into the core kernel lifecycle, ensuring that all dependent services (Database, LLM Router, Telemetry) are initialized with resolved credentials.

---

## 2. Scope & Boundaries

### In Scope
- **AES-256-GCM Encryption**: Transition `VaultManager` encryption from custom XOR cipher to standard AES-256-GCM (using `cryptography.hazmat.primitives.ciphers.aead.AESGCM`) with 12-byte random nonces.
- **Hashed Key Names**: Hash metadata keys using SHA-256 (`hashlib.sha256`) before persistence, hiding secret identifiers (like `openai_api_key`) from raw vault inspections.
- **Symmetric Key Persistence**: Maintain master key file persistence under `secrets/master.key` (or configurable path).
- **Secrets Serialization**: Persist the encrypted secrets dictionary to a JSON file (`secrets/vault.enc`) configured in settings.
- **Config Reference Resolution**: Implement dynamic resolution of settings string values matching `vault://<secret_name>` at kernel boot time, enabling password-less static configs.
- **WebSocket Handshake Authentication**: Authenticate connections to `/ws/v1/telemetry/stream` by parsing and validating query parameters or subprotocols as JWT tokens or API Keys, verifying revocation status and checking for the `"audit.read"` permission.
- **Observability Routes Protection**: Secure `/traces`, `/budget`, and `/health` endpoints using `Depends(require_permissions(["audit.read"]))`.

### Out of Scope (Non-Goals)
- ❌ Third-party secret management integration (HashiCorp Vault, AWS Secrets Manager) in this phase.
- ❌ Dynamic runtime mutation of master keys.
- ❌ Hardware Security Module (HSM) integrations.

---

## 3. Vault Persistence and Cipher Specifications

### 3.1 Encryption Algorithm: AES-256-GCM
- **Key Length**: 256 bits (32 bytes), read/generated under `secrets/master.key`.
- **Nonce (Initialization Vector)**: 12-byte random bytes generated per encryption call (`os.urandom(12)`).
- **Associated Data (Auth Data)**: Optional associated data to bind ciphertext context (defaults to `None`).
- **Ciphertext Output Format**: Base64-encoded string concatenation of `nonce(12 bytes) + ciphertext + tag`.

### 3.2 Key Hashing Schema
Before storing any key-value pair in the local vault file, the key is hashed to prevent metadata leakage:
```python
key_hash = hashlib.sha256(key_name.encode("utf-8")).hexdigest()
```
The vault payload structure saved to disk under `secrets/vault.enc` follows this JSON format:
```json
{
    "8543fe6b...d720": "base64_encoded_nonce_ciphertext_tag_blob...",
    "a789bcde...ef01": "base64_encoded_nonce_ciphertext_tag_blob..."
}
```

---

## 4. Component Contracts

### 4.1 VaultManager

```python
class VaultManager:
    """Manager for securely storing and retrieving secrets using local AES-256-GCM symmetric encryption."""

    def __init__(self, key_path: str, secrets_path: Optional[str] = None) -> None:
        """Initialize VaultManager with master key path and optional encrypted secrets path."""

    async def initialize(self) -> None:
        """Load or generate the 256-bit symmetric master key, and load existing secrets from disk."""

    def get_secret(self, key_name: str, agent_id: Optional[UUID] = None) -> str:
        """Retrieve, decrypt, and return a secret from the vault."""

    def set_secret(self, key_name: str, secret_value: str) -> None:
        """Encrypt and store a secret in the vault, writing the updated payload to disk."""
```

### 4.2 Dynamic Reference Resolution in Kernel

```python
class Kernel:
    # Existing methods...

    def _resolve_vault_secrets(self) -> None:
        """Scan all settings sub-models and replace any 'vault://secret_name' strings with resolved secrets."""
```

---

## 5. Security & Auth Middleware Integration

### 5.1 Telemetry WebSocket Handshake
The WebSocket endpoint at `/ws/v1/telemetry/stream` validates client credentials before upgrading the connection:
1. Parse the token query parameter: `/ws/v1/telemetry/stream?token=<token_value>`.
2. Determine token type:
   - If the token decodes as a JWT, verify signature, expiration, and check `RevocationService.is_token_revoked()`.
   - If the token is an API key, check `SecurityRepository.get_api_key_by_hashed()` and verify using `ApiKeyService`.
3. Resolve permissions using `RbacService`. Verify that permissions contain `"audit.read"`.
4. If authentication or authorization fails, close the socket with code `4001` (Unauthorized) or `4003` (Forbidden).

### 5.2 Observability REST Endpoints
Secure the following routes under `api/routes/observability.py`:
- `GET /api/v1/observability/traces` -> `Depends(require_permissions(["audit.read"]))`
- `GET /api/v1/observability/budget` -> `Depends(require_permissions(["audit.read"]))`
- `GET /api/v1/observability/health` -> `Depends(require_permissions(["audit.read"]))`

---

## 6. Verification and Acceptance Criteria

### Automated Test Suite Requirements
- **AES-GCM cipher round-trip**: Validate that data encrypted by the upgraded vault is successfully decrypted, and that tampering with the Base64 payload or tag results in an decryption error.
- **Hashed key indexing**: Verify that secret names are stored as SHA-256 hashes on disk, and cannot be found in plaintext in the vault file.
- **Secrets persistence**: Write secrets, restart/re-instantiate `VaultManager`, and verify that secrets are loaded correctly from disk.
- **Reference resolution**: Mock a vault secret `db_password = "secure_pass"`, configure `settings.database.password = "vault://db_password"`, and verify that boot-time resolution updates the settings value.
- **WebSocket authentication**: Test that connecting with:
  - No token returns 4001.
  - Invalid/expired token returns 4001.
  - Revoked token returns 4001.
  - Valid token but lacking `audit.read` permission returns 4001/4003.
  - Valid token and `audit.read` permission connects successfully.
- **Observability REST auth**: Verify that calling traces/budget/health without valid JWT/API-key headers returns 401 Unauthorized, and with valid headers but insufficient scopes returns 403 Forbidden.

### Quality Gate Requirements
- Strict mypy checks on all modified modules.
- Ruff format and lint clean check.
- Complete system verification suite: **≥ 1075 passed tests** (representing at least 20 new tests).
- Affected coverage must meet $\ge 80\%$ (100% on new security code).
