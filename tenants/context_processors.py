"""
Admin platform navigation.

Injects the operator links and real counts into every admin template. Without
this, `/admin/ecosystem/` is unreachable by clicking: the Django admin builds
its index purely from registered ModelAdmins, and these pages are plain views,
so nothing ever links to them.

Only staff get a payload at all, and the console links are only marked
available for superusers, because `tenants.views` restricts them to
`is_superuser`. A non-superuser staff member therefore does not get pointed at
a page that would 403 them.
"""

from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse


def platform_admin(request):
    """Add `platform` (nav links) and `platform_counts` to the admin context."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_staff:
        return {}

    from tenants.models import Organization

    def _safe(name):
        try:
            return reverse(name)
        except NoReverseMatch:
            return None

    is_super = user.is_superuser

    # Counts are shown on the admin index tiles. A failure here must not take
    # the whole admin down, so each count is guarded independently.
    counts = {"users": None, "jobs": None, "organizations": None, "tenants_active": None}
    try:
        counts["users"] = get_user_model().objects.count()
    except Exception:
        pass
    try:
        from jobs.models import JobPost

        counts["jobs"] = JobPost.objects.count()
    except Exception:
        pass
    try:
        counts["organizations"] = Organization.objects.count()
        counts["tenants_active"] = Organization.objects.filter(status="active").count()
    except Exception:
        pass

    return {
        "platform_counts": counts,
        "platform": {
            "ecosystem": _safe("admin:ecosystem"),
            "console": _safe("tenants:console_dashboard"),
            "console_orgs": _safe("tenants:console_organizations"),
            "console_plans": _safe("tenants:console_plans"),
            "workspaces": _safe("tenants:workspace_list"),
            "admin_models": _safe("admin:tenants_organization_changelist"),
            "is_superuser": is_super,
            "show_console": is_super,
            # Current page, so the admin sidebar can mark the active app and
            # model rather than highlighting nothing.
            "current_url": request.path,
            "current_app": _current_app_label(request.path),
        },
    }


def _current_app_label(path):
    """app_label owning an admin path, or '' when not under /admin/."""
    parts = [p for p in path.split("/") if p]
    # /admin/<app_label>/...
    if len(parts) >= 2 and parts[0] == "admin":
        return parts[1]
    return ""
