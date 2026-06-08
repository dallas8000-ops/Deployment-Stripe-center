"""License issuance via Stripe webhooks."""

import logging

import stripe
from django.conf import settings

from .models import License
from .utils import generate_license_key, normalize_domain, validate_domain_format

logger = logging.getLogger(__name__)


def _get_stripe():
    stripe.api_key = settings.SAAS_STRIPE_SECRET_KEY
    return stripe


def issue_license_for_subscription(stripe_sub_data: dict, customer_email: str, domain: str) -> License:
    """Issue a new license for a Stripe subscription."""
    if not validate_domain_format(domain):
        logger.error(f"Invalid domain format for license issuance: {domain}")
        raise ValueError(f"Invalid domain format: {domain}")

    subscription_id = stripe_sub_data.get("id", "")
    customer_id = stripe_sub_data.get("customer")
    if customer_id:
        customer_id = customer_id if isinstance(customer_id, str) else str(customer_id)

    # Check if license already exists for this subscription
    existing = License.objects.filter(stripe_subscription_id=subscription_id).first()
    if existing:
        logger.info(f"License already exists for subscription {subscription_id}")
        return existing

    # Generate license key
    license_key = generate_license_key()

    # Create license
    license_obj = License.objects.create(
        key=license_key,
        customer_email=customer_email,
        stripe_subscription_id=subscription_id,
        stripe_customer_id=customer_id or "",
        registered_domain=domain,
        max_instances=1,  # Flat monthly = 1 instance
        status=License.Status.ACTIVE,
    )

    logger.info(f"License issued: {license_key[:8]}... for {customer_email} (subscription: {subscription_id})")
    _send_license_email(license_obj)
    return license_obj


def _send_license_email(license_obj: License) -> None:
    from django.conf import settings
    from django.core.mail import send_mail

    if not getattr(settings, "LICENSE_EMAIL_ENABLED", True):
        return
    subject = "Your Stripe Installer license key"
    body = (
        f"Thank you for subscribing to Stripe Installer.\n\n"
        f"License key:\n{license_obj.key}\n\n"
        f"Registered domain: {license_obj.registered_domain}\n\n"
        f"Add to your deployed instance .env:\n"
        f"  STRIPE_INSTALLER_LICENSE_KEY={license_obj.key}\n"
        f"  STRIPE_INSTALLER_DOMAIN={license_obj.registered_domain}\n"
        f"  STRIPE_INSTALLER_VALIDATION_SERVER=<your-licensing-server>\n"
        f"  LICENSE_ENFORCEMENT_ENABLED=true\n"
    )
    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost"),
            [license_obj.customer_email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.warning("Could not email license key: %s", exc)


def revoke_license_for_subscription(stripe_sub_data: dict) -> None:
    """Revoke license when subscription is cancelled/deleted."""
    subscription_id = stripe_sub_data.get("id", "")
    
    try:
        license_obj = License.objects.get(stripe_subscription_id=subscription_id)
        license_obj.status = License.Status.REVOKED
        license_obj.save(update_fields=["status", "updated_at"])
        logger.info(f"License revoked for subscription {subscription_id}: {license_obj.key[:8]}...")
    except License.DoesNotExist:
        logger.warning(f"No license found for subscription {subscription_id}")


def handle_checkout_session_completed(session: dict) -> None:
    """Handle checkout.session.completed webhook to issue license."""
    _get_stripe()
    
    subscription_id = session.get("subscription")
    if not subscription_id:
        logger.info("No subscription in checkout session, skipping license issuance")
        return

    # Get subscription details
    stripe_sub = stripe.Subscription.retrieve(subscription_id)
    
    # Get customer email
    customer_id = session.get("customer")
    if customer_id:
        customer_id = customer_id if isinstance(customer_id, str) else str(customer_id)
        customer = stripe.Customer.retrieve(customer_id)
        customer_email = customer.get("email", "")
    else:
        customer_email = ""

    # Get domain from metadata
    metadata = session.get("metadata", {}) or {}
    domain = normalize_domain(metadata.get("domain") or "")

    if not domain:
        logger.error(f"No domain provided in checkout session metadata for subscription {subscription_id}")
        return

    try:
        issue_license_for_subscription(stripe_sub, customer_email, domain)
    except ValueError as exc:
        logger.exception(f"Failed to issue license: {exc}")


def handle_subscription_deleted(stripe_sub: dict) -> None:
    """Handle customer.subscription.deleted webhook to revoke license."""
    revoke_license_for_subscription(stripe_sub)
