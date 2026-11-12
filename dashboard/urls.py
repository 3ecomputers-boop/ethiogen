from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('subscriptions/', views.subscriptions, name='subscriptions'),
    path('subscriptions/<int:pk>/<str:action>/', views.subscription_action, name='subscription_action'),
    path('posts/', views.posts, name='posts'),
    path('posts/<int:pk>/publish/', views.post_publish, name='post_publish'),
    path('users/', views.users, name='users'),
    path('organizations/', views.organizations, name='organizations'),
    path('job-seekers/', views.job_seekers, name='job_seekers'),
    path('applications/', views.applications, name='applications'),
    path('settings/', views.settings_view, name='settings'),
    path('settings/save/', views.settings_save, name='settings_save'),
    path('admin-models/', views.admin_models, name='admin_models'),
]