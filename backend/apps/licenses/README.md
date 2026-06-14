# Stripe Installer License System

## Overview

The license system provides license issuance and instance validation for Stripe Installer deployments. It enforces the $79/mo flat-rate pricing model by requiring customers to have valid licenses to run their Stripe Installer instances.

## Architecture

### License Issuance Flow

```
Customer pays via Stripe Checkout
        ↓
Stripe webhook fires → generate unique license key
        ↓
License key stored in DB tied to:
  - customer email
  - subscription ID
  - registered domain (they provide on signup)
  - max instance count (1 per flat monthly)
        ↓
Customer receives license key via email
```

### Instance Validation Flow

```
Customer deploys Stripe Installer
        ↓
On startup → app calls home to your validation endpoint:
  POST /api/v1/license/validate
  { license_key, domain, instance_id }
        ↓
Your server checks:
  ✓ Key exists and is active
  ✓ Domain matches registered domain
  ✓ Instance count not exceeded
        ↓
Returns: valid/invalid + expiry date
        ↓
App re-validates every 24hrs (silent background check)
```

## Backend Components

### Models

#### License Model
- `key`: Cryptographically secure 64-character license key
- `customer_email`: Customer's email address
- `stripe_subscription_id`: Associated Stripe subscription
- `stripe_customer_id`: Associated Stripe customer
- `registered_domain`: Domain where license is valid
- `max_instances`: Maximum allowed instances (default: 1)
- `status`: active, suspended, revoked, expired
- `expiry_date`: Optional expiry date

#### InstanceRegistry Model
- `instance_id`: Unique instance identifier
- `license`: Foreign key to License
- `domain`: Domain where instance is running
- `last_seen`: Timestamp of last validation
- `first_registered`: Timestamp when instance first registered
- `user_agent`: User agent string
- `ip_address`: IP address of instance

### API Endpoints

#### POST /api/v1/license/validate
Validates a license key for an instance.

**Request:**
```json
{
  "license_key": "your-license-key",
  "domain": "your-domain.com",
  "instance_id": "unique-instance-id"
}
```

**Response (valid):**
```json
{
  "valid": true,
  "expiry_date": "2024-12-31T23:59:59Z",
  "max_instances": 1,
  "active_instances": 1,
  "message": "License valid"
}
```

**Response (invalid):**
```json
{
  "valid": false,
  "message": "License invalid - reason"
}
```

#### GET /api/v1/license/<license_key>/
Admin endpoint to view license details (requires authentication).

#### POST /api/v1/license/<license_key>/revoke/
Admin endpoint to revoke a license (requires authentication).

### Webhook Integration

The license system integrates with the existing Stripe billing webhooks:

- `checkout.session.completed`: Issues a new license when customer completes checkout
- `customer.subscription.deleted`: Revokes license when subscription is cancelled

**Important:** The checkout session must include `domain` in metadata for license issuance.

## Client-Side Validation

### LicenseValidator Class

The `client_validation.py` module provides a `LicenseValidator` class for deployed instances:

```python
from apps.licenses.client_validation import LicenseValidator

validator = LicenseValidator(
    license_key="your-license-key",
    domain="your-domain.com",
    validation_server="https://your-app.up.railway.app"
)

if validator.validate():
    print("License valid!")
else:
    print("License invalid!")
```

### Startup Validation

Convenience function for startup validation:

```python
from apps.licenses.client_validation import validate_on_startup

# Reads from environment variables:
# STRIPE_INSTALLER_LICENSE_KEY
# STRIPE_INSTALLER_DOMAIN
# STRIPE_INSTALLER_VALIDATION_SERVER

if validate_on_startup():
    print("License valid, starting application...")
else:
    print("License invalid, cannot start")
```

### Background Validation

Start background thread for periodic validation:

```python
validator = LicenseValidator(...)
validator.start_background_validation(interval_hours=24)
```

### Decorator for Protected Functions

```python
from apps.licenses.client_validation import require_valid_license

@require_valid_license
def protected_function():
    # This will only run if license is valid
    pass
```

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Stripe billing (required for license issuance)
SAAS_STRIPE_SECRET_KEY=sk_live_...
SAAS_STRIPE_WEBHOOK_SECRET=whsec_...
SAAS_STRIPE_PRICE_STARTER=price_...
SAAS_STRIPE_PRICE_PRO=price_...
SAAS_STRIPE_PRICE_ENTERPRISE=price_...
SAAS_BILLING_RETURN_URL=https://your-app.com/billing

# License enforcement (optional, for deployed instances)
LICENSE_ENFORCEMENT_ENABLED=true
LICENSE_ENFORCEMENT_MODE=readonly  # or "block"
LICENSE_READ_ONLY_MESSAGE="License invalid - running in read-only mode"
```

### Client-Side Environment Variables

For deployed instances:

```bash
STRIPE_INSTALLER_LICENSE_KEY=your-license-key
STRIPE_INSTALLER_DOMAIN=your-domain.com
STRIPE_INSTALLER_VALIDATION_SERVER=https://your-app.up.railway.app
```

## Stripe Checkout Integration

When creating a Stripe checkout session, include the domain in metadata:

```python
session_params = {
    "mode": "subscription",
    "line_items": [{"price": price_id, "quantity": 1}],
    "metadata": {
        "domain": "customer-domain.com"  # Required for license issuance
    },
    # ... other params
}
```

## Graceful Degradation

The system supports two enforcement modes:

### Read-Only Mode (default)
- Application continues running but in read-only mode
- Prevents write operations
- Adds `X-License-Status: invalid` header to responses
- Allows customers to export data before renewal

### Block Mode
- Blocks all access with 403 error
- Returns error message: "License invalid - access denied"

## Pricing

The license system enforces a flat monthly pricing of **$79/mo per customer**.

This pricing is justified because:
- Stripe Installer handles Stripe setup, vault management, agency tooling, and full deploy pipeline
- License enforcement provides a protected, dedicated instance
- Serious value proposition for dev/agency space (typical range: $49–$149/mo)

## Admin Interface

License management is available in the Django admin at `/admin/licenses/`:

- View all licenses
- See registered instances per license
- Revoke licenses
- Monitor instance activity

## Security Considerations

1. **License Keys**: Generated using `secrets.token_urlsafe(48)` for cryptographic security
2. **Domain Validation**: Strict domain matching prevents license sharing
3. **Instance Limits**: Enforces 1 instance per license (configurable)
4. **Webhook Verification**: Stripe signature verification prevents spoofing
5. **Grace Period**: 48-hour grace period for network failures

## Monitoring

The system logs important events:

- License issuance
- License validation (success/failure)
- License revocation
- Instance registration
- Domain mismatches
- Instance limit violations

## Troubleshooting

### License validation fails
- Check that the domain matches the registered domain
- Verify the license key is correct
- Ensure the subscription is active
- Check instance count hasn't exceeded limit

### License not issued on checkout
- Verify `domain` is included in checkout session metadata
- Check webhook logs for errors
- Ensure Stripe webhook secret is configured

### Instance marked as inactive
- Instance is considered inactive if not seen within 48 hours
- Background validation should update `last_seen` timestamp
- Check network connectivity to validation server

## Future Enhancements

Potential improvements:
- Multi-domain support per license
- Tiered instance limits (e.g., 1, 5, 10 instances)
- License transfer between domains
- Usage-based analytics
- License renewal reminders
- API for manual license issuance
