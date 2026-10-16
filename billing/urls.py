from django.urls import path

from . import employer_api, views
from .views import telegram_login

app_name = 'billing'

urlpatterns = [
    # Payments
    path('chapa/webhook/', views.chapa_webhook, name='chapa_webhook'),

    # Telegram Web App one-tap sign-in
    path('auth/telegram/', telegram_login, name='telegram_login'),

    # Alert preferences (all three modes)
    path('api/alerts/preferences/', employer_api.get_alert_preferences,
         name='alert_preferences'),
    path('api/alerts/preferences/set/', employer_api.set_alert_preferences,
         name='alert_preferences_set'),

    # Employer tools
    path('api/employer/post-job/', employer_api.employer_post_job,
         name='employer_post_job'),
    path('api/employer/my-posts/', employer_api.employer_my_posts,
         name='employer_my_posts'),
    path('api/employer/applications/', employer_api.employer_applications,
         name='employer_applications'),
    path('api/employer/applications/<int:application_id>/',
         employer_api.employer_update_application,
         name='employer_update_application'),
]
