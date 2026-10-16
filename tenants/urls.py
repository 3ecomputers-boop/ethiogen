from django.urls import path

from . import api, views

app_name = 'tenants'

urlpatterns = [
    # ------------------------------------------------------------------
    # Employer workspace (membership-scoped server-rendered pages)
    # ------------------------------------------------------------------
    path('workspaces/', views.workspace_list, name='workspace_list'),
    path('workspaces/new/', views.workspace_create, name='workspace_create'),
    path('workspaces/<slug:slug>/', views.workspace_detail, name='workspace_detail'),
    path('workspaces/<slug:slug>/members/', views.workspace_members,
         name='workspace_members'),
    path('workspaces/<slug:slug>/members/invite/', views.workspace_invite,
         name='workspace_invite'),
    path('workspaces/<slug:slug>/members/<int:user_id>/role/',
         views.workspace_change_role, name='workspace_change_role'),
    path('workspaces/<slug:slug>/members/<int:user_id>/remove/',
         views.workspace_remove_member, name='workspace_remove_member'),
    path('workspaces/<slug:slug>/billing/', views.workspace_billing,
         name='workspace_billing'),
    path('workspaces/<slug:slug>/jobs/', views.workspace_jobs,
         name='workspace_jobs'),
    path('invitations/<uuid:token>/', views.accept_invitation,
         name='accept_invitation'),

    # ------------------------------------------------------------------
    # Operator console (superuser only)
    # ------------------------------------------------------------------
    path('console/', views.console_dashboard, name='console_dashboard'),
    path('console/organizations/', views.console_organizations,
         name='console_organizations'),
    path('console/organizations/<int:pk>/', views.console_organization_detail,
         name='console_organization_detail'),
    path('console/plans/', views.console_plans, name='console_plans'),

    # ------------------------------------------------------------------
    # JSON API (existing)
    # ------------------------------------------------------------------
    # Public
    path('api/plans/', api.list_plans, name='list_plans'),

    # Organizations
    path('api/organizations/', api.list_organizations, name='list_organizations'),
    path('api/organizations/create/', api.create_organization, name='create_organization'),
    path('api/organizations/<slug:slug>/', api.organization_detail,
         name='organization_detail'),
    path('api/organizations/<slug:slug>/dashboard/', api.organization_dashboard,
         name='organization_dashboard'),
    path('api/organizations/<slug:slug>/quota/', api.organization_quota,
         name='organization_quota'),

    # Members
    path('api/organizations/<slug:slug>/members/', api.list_members,
         name='list_members'),
    path('api/organizations/<slug:slug>/members/invite/', api.invite_member,
         name='invite_member'),
    path('api/organizations/<slug:slug>/members/<int:user_id>/role/',
         api.change_member_role, name='change_member_role'),
    path('api/organizations/<slug:slug>/members/<int:user_id>/remove/',
         api.remove_member, name='remove_member'),

    # Invitations
    path('api/invitations/', api.my_invitations, name='my_invitations'),
    path('api/invitations/<uuid:token>/accept/', api.accept_invitation,
         name='api_accept_invitation'),
]