# Data Processing Agreement — outline

Template outline for enterprise customers. **Have legal counsel review** before execution.

## 1. Definitions

- **Controller**: Customer organization using Automation Center.
- **Processor**: Operator of the Automation Center SaaS instance.
- **Personal Data**: User emails, names, audit actors, billing contact data.
- **Customer Content**: Project metadata, encrypted vault blobs, transfer plans (secrets redacted in audit logs).

## 2. Scope and purpose

Processor processes Personal Data only to provide: project management, encrypted secret storage, deployment/transfer automation, Stripe setup automation, and audit logging.

## 3. Subprocessors

Listed in [SUBPROCESSORS.md](SUBPROCESSORS.md). Processor will provide 30-day notice of material additions.

## 4. Security measures

- Encryption at rest for vault secrets (AES-GCM, customer-independent master key per deployment).
- TLS for data in transit.
- MFA and optional OIDC SSO.
- Tamper-evident transfer audit chain.
- Access logging on project and transfer actions.

## 5. Data retention and deletion

| Data type | Default retention | Deletion |
|-----------|-------------------|----------|
| Project audit logs | `AUDIT_LOG_RETENTION_DAYS` (365) | Auto-prune + on org delete |
| Transfer audit chain | `TRANSFER_AUDIT_RETENTION_DAYS` (2555) | Export + manual prune |
| Vault secrets | Until customer deletes project/org | Crypto-shredding via key rotation policy |
| Account | Until account deletion request | Django user delete cascade |

## 6. Data subject requests

Controller is responsible for identifying data subjects. Processor will assist with export/delete within **30 days** of verified request.

## 7. Breach notification

Processor notifies Controller without undue delay and no later than **72 hours** after becoming aware of a Personal Data breach affecting Controller data.

## 8. Audits

Controller may request SOC 2 report or security questionnaire annually. On-site audits by mutual agreement with reasonable notice.

## 9. International transfers

Standard Contractual Clauses or equivalent mechanism where required. Subprocessor list includes processing locations.
