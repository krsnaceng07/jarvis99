# 91_PHASE_29_ADVANCED_VAULT_OPERATIONS_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 29: Advanced Vault Operations**. It adds cryptographic key rotation capability, secure backup/restore pipelines, secret expiration tracking, and non-sensitive audit logging for vault read, write, and rotation actions.

## Status
**STATUS:** FROZEN (2026-07-04) | 1073 passed
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 28

---

## 1. Architectural Position

Phase 29 adds runtime administration and operational utilities to the frozen security layer:

```
        Client Request (REST Admin)
                     │
                     ▼
          FastAPI Router (/api/v1/vault/*)
       ┌────────────────────────────────────────────────────────┐
       │ Requires permission: "vault.admin"                     │
       └─────────────────────┬──────────────────────────────────┘
                             │
                             ▼
                     Security Service
       ┌────────────────────────────────────────────────────────┐
       │ VaultManager (Rotate Keys / Backup / Restore)           │
       └─────────────────────┬──────────────────────────────────┘
                             │
                             ▼
                         Auditing
       ┌────────────────────────────────────────────────────────┐
       │ Dispatch event to Telemetry / Audit logs               │
       │ (e.g., event: "vault.secret_accessed")                 │
       └────────────────────────────────────────────────────────┘
```

---

## 2. Scope & Boundaries

### In Scope
- **Cryptographic Key Rotation**: Implement a key rotation function in `VaultManager` that generates a new 256-bit symmetric key, decrypts all existing entries using their current `key_id`, re-encrypts them using the new key, assigns a new `key_id`, and atomically writes both the new key and the re-encrypted vault entries to disk.
- **Vault Backup/Restore**: Support exporting the entire encrypted vault payload along with its metadata, and importing/restoring it after validating version compatibility and integrity checks.
- **Secret Expiration Metadata**: Add an optional `expires_at` ISO-timestamp field to the secret entries metadata, enabling automated checks for credential expiration.
- **Non-Sensitive Vault Auditing**: Log key access, storage, and rotation events to the global event bus. Ensure that plaintext secret values and encryption keys are **never** logged.
- **Admin REST API Routes**: Introduce `/api/v1/vault/rotate` and `/api/v1/vault/backup` admin routes protected by `"vault.admin"` permission.

---

## 3. Vault Entry Schema Upgrades

The version 2 JSON schema is extended to support expiration and key ID tracking:

```json
{
  "version": 2,
  "created_at": "2026-07-04T13:30:00Z",
  "entries": {
    "8543fe6b...d720": {
      "ciphertext": "base64_encoded_nonce_ciphertext_tag_blob...",
      "key_id": "master_key_v2",
      "algorithm": "AES-256-GCM",
      "created_at": "2026-07-04T13:30:00Z",
      "expires_at": "2026-08-04T13:30:00Z"
    }
  }
}
```

---

## 4. Component Contracts

### 4.1 VaultManager Additions

```python
class VaultManager:
    # Existing methods...

    async def rotate_master_key(self) -> str:
        """Generate a new master key, re-encrypt all secrets, and persist them.

        Returns:
            The newly active key_id string.
        """

    def check_expiration(self, key_name: str) -> bool:
        """Check if the given secret has expired.

        Returns:
            True if expired, False otherwise.
        """
```

---

## 5. Security & Auth Middleware Integration

### 5.1 Admin Endpoints
Introduce routes in `api/routes/vault.py` protected by `"vault.admin"` permission:
- `POST /api/v1/vault/rotate` -> Trigger key rotation.
- `POST /api/v1/vault/backup` -> Export encrypted vault.
- `POST /api/v1/vault/restore` -> Restore vault from backup payload.

---

## 6. Verification and Acceptance Criteria

### Automated Test Suite Requirements
- **Key Rotation**: Validate that rotating the key successfully replaces the master key file on disk, re-encrypts all existing entries, updates their `key_id`, and that old keys can no longer decrypt the updated vault.
- **Expiration Enforcement**: Store a secret with a past expiration date and verify that `check_expiration()` returns `True`, and that trying to fetch it warns the system.
- **Backup & Restore**: Export a vault state, mutate the vault, restore it, and verify the original state is recovered.
- **No Sensitive Leakage**: Assert that all test logs generated during vault operations contain zero occurrences of secret values.
- **Admin Scopes**: Verify that only clients with `"vault.admin"` permission can invoke the rotation/backup APIs.
