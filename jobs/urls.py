from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import dashboard_metrics_api
from .views import add_job_seeker, dashboard_metrics,verify_job_seeker

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
    path('employer-dashboard/', views.employer_dashboard, name='employer_dashboard'),  # ✅ correct name (underscore)
    path('checkout/', views.checkout, name='checkout'),
    path('pay-for-talent/<int:talent_id>/', views.pay_for_contact, name='pay_for_contact'),

    # ----- Reviews -----
    path('jobs/<int:job_id>/review/<int:service_provider_id>/', views.create_review, name='create_review'),

    # ----- AJAX / Session endpoints -----
    path('hire-request/', views.submit_hire_request, name='hire_request'),
    path('post-need/', views.submit_post_need, name='post_need'),
    # update-session with both names (primary + alias for backwards compatibility)
    path('update-session/', views.update_session_state, name='update_session_state'),
    path('update-session/', views.update_session_state, name='update_session'),

    # ----- Authentication -----
    path('change-password/', auth_views.PasswordChangeView.as_view(
        template_name='registration/change_password.html',
        success_url='/dashboard/'
    ), name='change_password'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),

    # ----- Admin / Construction -----
    path('construction/', views.construction_dashboard, name='construction_dashboard'),
    path('admin/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('api/dashboard-metrics/', dashboard_metrics_api, name='dashboard_metrics_api'),
     path('api/admin/add-job-seeker/', add_job_seeker, name='add_job_seeker'),
    path('api/dashboard-metrics/', dashboard_metrics, name='dashboard_metrics'),

     path('', views.home, name='home'),
    path('dashboard/', views.job_seeker_dashboard, name='job_seeker_dashboard'),
    path('profile/create/', views.create_job_seeker_profile, name='create_job_seeker_profile'),
    path('profile/<int:pk>/', views.view_job_seeker_profile, name='view_job_seeker_profile'),
    path('browse/', views.browse_job_seekers, name='browse_job_seekers'),
    path('jobs/', views.list_jobs, name='list_jobs'),
    path('jobs/<int:job_id>/', views.job_details, name='job_details'),
    path('client/profile/', views.client_profile, name='client_profile'),
    path('client/dashboard/', views.client_dashboard, name='client_dashboard'),
    path('staff-dashboard/', views.staff_dashboard, name='staff_dashboard'),
    
    # API Endpoints
    path('api/job-seekers/', views.api_job_seekers, name='api_job_seekers'),
    path('api/talents/', views.api_talents, name='api_talents'),
    path('api/register/seeker/', views.api_register_seeker, name='api_register_seeker'),
    path('api/register/employer/', views.api_register_employer, name='api_register_employer'),
    path('api/login/seeker/', views.api_seeker_login, name='api_seeker_login'),
    path('api/login/employer/', views.api_employer_login, name='api_employer_login'),
    path('api/dashboard-metrics/', views.dashboard_metrics, name='dashboard_metrics'),
    path('api/admin/add-job-seeker/', views.add_job_seeker, name='add_job_seeker'),
    
    # Other
    path('language/<str:language>/', views.change_language, name='change_language'),
    path('hire-request/', views.submit_hire_request, name='hire_request'),
    path('post-need/', views.submit_post_need, name='post_need'),
    path('update-session/', views.update_session_state, name='update_session'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('resend-otp/', views.resend_otp_view, name='resend_otp'),
    path('api/dashboard-metrics/', dashboard_metrics_api, name='dashboard_metrics'),
    path('api/admin/add-job-seeker/', add_job_seeker, name='add_job_seeker'),
    path('api/admin/verify-job-seeker/', verify_job_seeker, name='verify_job_seeker'),
    path('api/talent/<int:talent_id>/update/', views.update_talent, name='update_talent'),
    path('api/talent/<int:talent_id>/', views.get_talent, name='get_talent'),
    
]