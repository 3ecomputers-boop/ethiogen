
from django.contrib import admin
from django.urls import path,include
from jobs.views import staff_dashboard  # import the view
from jobs.views import api_toggle_verify

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
#from jobs.views import mini_app   # ✅ Add this line
from jobs.views import (
    mini_app,
    api_register_seeker,
    api_register_employer,
    api_login,
    api_current_user,
    api_job_seekers,
)
from jobs.views import verify_job_seeker
from jobs.views import telegram_webhook
from jobs import urls as jobs_urls

urlpatterns = [
    path('admin/dashboard/', staff_dashboard, name='staff_dashboard'),
    path('admin/', admin.site.urls),

    # Include jobs.urls WITHOUT a namespace here, so templates can use the
    # short form {% url 'home' %} as well as {% url 'jobs:home' %}.
    # employers.urls also includes jobs.urls and that copy owns the 'jobs'
    # namespace; including it twice WITH a namespace is what produced
    # "urls.W005: URL namespace 'jobs' isn't unique".
    path('', include((jobs_urls.urlpatterns, None))),

    path('', include('accounts.urls')),
    path('',include('freelancer.urls')),
    path('',include('employers.urls')),
    path('telegram-webhook/', telegram_webhook, name='telegram_webhook'),
   # urls.py
    path('miniapp/', mini_app, name='mini_app'),
    path('api/register/seeker/', api_register_seeker, name='api_register_seeker'),
    path('api/register/employer/', api_register_employer, name='api_register_employer'),
     path('api/login/', api_login, name='api_login'),  # ✅ Add this
    path('api/current-user/', api_current_user, name='api_current_user'),
    path('api/job-seekers/', api_job_seekers, name='api_job_seekers'),
    path('tg/wh/', telegram_webhook, name='telegram_webhook'),  # ✅ Webhook (POST only)
    path('recruitment/', include('recruitment.urls')), 
    path('billing/', include('billing.urls')),
    path('tenants/', include('tenants.urls')),
    path('api/job-seekers/<int:seeker_id>/toggle-verify/', api_toggle_verify, name='api_toggle_verify'),
    path('api/admin/verify-job-seeker/', verify_job_seeker, name='verify_job_seeker'),
]
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )