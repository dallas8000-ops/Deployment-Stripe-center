from rest_framework import serializers

from apps.core.access import ROLE_RANK, org_membership
from apps.runs.models import PipelineRun

from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    latest_readiness_score = serializers.SerializerMethodField()
    last_run_status = serializers.SerializerMethodField()
    production_url = serializers.SerializerMethodField()
    active_environment = serializers.SerializerMethodField()
    organization_slug = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    org_billing = serializers.SerializerMethodField()
    stripe_exempt = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "git_url",
            "local_path",
            "framework",
            "language",
            "scan_data",
            "last_scanned_at",
            "created_at",
            "updated_at",
            "latest_readiness_score",
            "last_run_status",
            "production_url",
            "active_environment",
            "organization_slug",
            "organization_name",
            "org_billing",
            "stripe_exempt",
        )
        read_only_fields = (
            "id",
            "slug",
            "framework",
            "language",
            "scan_data",
            "last_scanned_at",
            "created_at",
            "updated_at",
            "latest_readiness_score",
            "last_run_status",
            "production_url",
            "active_environment",
        )

    def get_active_environment(self, obj: Project) -> str:
        return obj.active_environment

    def get_organization_slug(self, obj: Project) -> str | None:
        return obj.organization.slug if obj.organization_id else None

    def get_organization_name(self, obj: Project) -> str | None:
        return obj.organization.name if obj.organization_id else None

    def get_stripe_exempt(self, obj: Project) -> bool:
        from apps.stripe_core.portfolio_catalog import is_stripe_exempt_slug

        return is_stripe_exempt_slug(obj.slug)

    def get_org_billing(self, obj: Project) -> dict | None:
        if not obj.organization_id:
            return None
        from django.conf import settings

        from apps.billing.enforcement import (
            free_member_limit,
            free_project_limit,
            org_billing_exempt,
            org_has_active_subscription,
        )

        org = obj.organization
        saas_configured = bool(getattr(settings, "SAAS_STRIPE_SECRET_KEY", ""))
        active = org_has_active_subscription(org) or org_billing_exempt(org)
        return {
            "saasConfigured": saas_configured,
            "subscriptionActive": active,
            "needsUpgrade": saas_configured and not active,
            "memberCount": org.memberships.count(),
            "projectCount": org.projects.count(),
            "freeMemberLimit": free_member_limit(),
            "freeProjectLimit": free_project_limit(),
        }

    def get_production_url(self, obj: Project) -> str:
        scan = obj.scan_data or {}
        return str(scan.get("productionUrl") or scan.get("production_url") or "")

    def get_latest_readiness_score(self, obj: Project) -> int | None:
        run = (
            PipelineRun.objects.filter(project=obj, status=PipelineRun.Status.COMPLETED)
            .order_by("-completed_at")
            .first()
        )
        if run and run.readiness_score is not None:
            return run.readiness_score
        scan = obj.scan_data or {}
        return scan.get("lastReadinessScore")

    def get_last_run_status(self, obj: Project) -> str | None:
        run = PipelineRun.objects.filter(project=obj).order_by("-created_at").first()
        if not run:
            return None
        if run.status == PipelineRun.Status.FAILED:
            score = self.get_latest_readiness_score(obj)
            if score is not None and score >= 75:
                return None
        return run.status


class ProjectUpdateSerializer(serializers.ModelSerializer):
    production_url = serializers.URLField(required=False, allow_blank=True)
    active_environment = serializers.ChoiceField(
        choices=("test", "staging", "production"),
        required=False,
    )
    organization_slug = serializers.SlugField(required=False, allow_blank=True)

    class Meta:
        model = Project
        fields = (
            "name",
            "description",
            "git_url",
            "local_path",
            "production_url",
            "active_environment",
            "organization_slug",
        )

    def update(self, instance: Project, validated_data):
        production_url = validated_data.pop("production_url", None)
        active_environment = validated_data.pop("active_environment", None)
        organization_slug = validated_data.pop("organization_slug", None)
        local_path = validated_data.get("local_path")
        if local_path is not None:
            from apps.stripe_core.portfolio_workspace import workspace_path_error

            err = workspace_path_error(instance, local_path.strip())
            if err:
                raise serializers.ValidationError({"local_path": err})
        instance = super().update(instance, validated_data)
        scan = dict(instance.scan_data or {})
        changed = False
        if production_url is not None:
            scan["productionUrl"] = production_url.rstrip("/") if production_url else ""
            changed = True
        if active_environment is not None:
            scan["activeEnvironment"] = active_environment
            changed = True
        if changed:
            instance.scan_data = scan
            instance.save(update_fields=["scan_data", "updated_at"])

        if local_path is not None and instance.local_path:
            from apps.deploy.platform_bootstrap import bootstrap_new_project

            request = self.context.get("request")
            if request and request.user.is_authenticated:
                try:
                    bootstrap_new_project(instance, user=request.user)
                except Exception:
                    pass

        if organization_slug is not None:
            request = self.context.get("request")
            if organization_slug == "":
                instance.organization = None
                instance.save(update_fields=["organization", "updated_at"])
            else:
                org = Organization.objects.filter(slug=organization_slug).first()
                if not org:
                    raise serializers.ValidationError({"organization_slug": "Organization not found"})
                membership = org_membership(request.user, org) if request else None
                if not membership or ROLE_RANK.get(membership.role, -1) < ROLE_RANK["admin"]:
                    raise serializers.ValidationError({"organization_slug": "Admin role required on organization"})
                if instance.organization_id != org.id:
                    from apps.billing.enforcement import BillingLimitError, assert_can_assign_org_project

                    try:
                        assert_can_assign_org_project(org)
                    except BillingLimitError as exc:
                        raise serializers.ValidationError({"organization_slug": str(exc)}) from exc
                instance.organization = org
                instance.save(update_fields=["organization", "updated_at"])
        return instance

    def to_representation(self, instance: Project):
        return ProjectSerializer(instance, context=self.context).data


class ProjectScanSerializer(serializers.Serializer):
    local_path = serializers.CharField(required=False, allow_blank=True, max_length=500)
