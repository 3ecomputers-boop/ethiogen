from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'jobs'

urlpatterns = [
    # ----- Public pages -----
    path('', views.home, name='home'),
    path('language/<str:language>/', views.change_language, name='change_language'),
    path('construction_workforce/', views.construction_workforce_page, name='construction_workforce'),
    path('business_consultancy/', views.business_consultancy_page, name='business_consultancy'),

    # ----- Registration & Verification -----
    path('register/job-seeker/', views.job_seeker_register, name='job_seeker_register'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('resend-otp/', views.resend_otp_view, name='resend_otp'),

    # ----- Job Seeker -----
    path('dashboard/', views.job_seeker_dashboard, name='job_seeker_dashboard'),
    path('profile/create/', views.create_job_seeker_profile, name='create_job_seeker_profile'),
    path('profile/<int:pk>/', views.view_job_seeker_profile, name='view_job_seeker_profile'),
    path('browse/', views.browse_job_seekers, name='browse_job_seekers'),

    # ----- Jobs -----
    path('jobs/add/', views.add_job, name='add_job'),
    path('jobs/', views.list_jobs, name='list_jobs'),
    path('jobs/<int:job_id>/', views.job_details, name='job_details'),

    # ----- Client / Employer -----
    path('client/profile/', views.client_profile, name='client_profile'),
    path('client/dashboard/', views.client_dashboard, name='client_dashboard'),
    path('client/jobs/create/', views.create_job_request, name='create_job_request'),

    # ----- Employer Dashboard & Checkout -----
    path('employer-dashboard/', views.employer_dashboard, name='employer_dashboard'),
    path('checkout/', views.checkout, name='checkout'),
    path('pay-for-talent/<int:talent_id>/', views.pay_for_contact, name='pay_for_contact'),

    # ----- Reviews -----
    path('jobs/<int:job_id>/review/<int:service_provider_id>/', views.create_review, name='create_review'),

    # ----- AJAX / Session endpoints -----
    path('hire-request/', views.submit_hire_request, name='hire_request'),
    path('post-need/', views.submit_post_need, name='post_need'),
    path('update-session/', views.update_session_state, name='update_session'),

    # ----- Staff & Admin -----
    path('admin/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('construction/', views.construction_dashboard, name='construction_dashboard'),

    # =========================================================================
    # API ENDPOINTS (all prefixed with /api/)
    # =========================================================================

    # Authentication
    path('api/login/', views.api_login, name='api_login'),
    path('api/logout/', views.api_logout, name='api_logout'),
    path('api/current-user/', views.api_current_user, name='api_current_user'),

    # Registration
    path('api/register/seeker/', views.api_register_seeker, name='api_register_seeker'),
    path('api/register/employer/', views.api_register_employer, name='api_register_employer'),

    # Job Seekers
    path('api/job-seekers/', views.api_job_seekers, name='api_job_seekers'),
    path('api/admin/add-job-seeker/', views.add_job_seeker, name='add_job_seeker'),
    path('api/admin/verify-job-seeker/', views.verify_job_seeker, name='verify_job_seeker'),
    path('api/job-seekers/<int:seeker_id>/toggle-verify/', views.api_toggle_verify, name='api_toggle_verify'),

    # Talents
    path('api/talents/', views.api_talents, name='api_talents'),
    path('api/talent/<int:talent_id>/', views.get_talent, name='get_talent'),
    path('api/talent/<int:talent_id>/update/', views.update_talent, name='update_talent'),
    path('api/talents/upload-photo/', views.api_upload_talent_photo, name='api_upload_talent_photo'),
    path('api/talents/remove-photo/', views.api_remove_talent_photo, name='api_remove_talent_photo'),
    path('api/talents/fix-images/', views.api_fix_talent_images, name='api_fix_talent_images'),

    # Jobs (JSON)
    path('api/jobs/', views.api_jobs, name='api_jobs'),
    path('api/jobs/<int:job_id>/', views.api_job_detail, name='api_job_detail'),

    # Dashboard metrics
    path('api/dashboard-metrics/', views.dashboard_metrics, name='dashboard_metrics'),

    # Categories
    path('api/categories/', views.api_categories, name='api_categories'),

    # ----- Telegram Webhook & Mini App -----
    path('telegram-webhook/', views.telegram_webhook, name='telegram_webhook'),
    path('mini-app/', views.mini_app, name='mini_app'),

    # ----- Authentication (built‑in) -----
    path('change-password/', auth_views.PasswordChangeView.as_view(
        template_name='registration/change_password.html',
        success_url='/dashboard/'
    ), name='change_password'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
]