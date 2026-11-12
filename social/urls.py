from django.urls import path

from . import views

app_name = 'social'

urlpatterns = [
    path('', views.feed, name='feed'),
    path('connections/', views.connections, name='connections'),
    path('connect/<int:user_id>/', views.connect, name='connect'),
    path('connections/<int:pk>/<str:action>/', views.connection_action, name='connection_action'),
    path('saved-jobs/', views.saved_jobs, name='saved_jobs'),
    path('save-job/<int:job_id>/', views.save_job, name='save_job'),
    path('unsave-job/<int:job_id>/', views.unsave_job, name='unsave_job'),
    path('notifications/', views.notifications, name='notifications'),
    path('inbox/', views.inbox, name='inbox'),
    path('like/<int:pk>/', views.like_post, name='like_post'),
    path('comment/<int:pk>/', views.comment_post, name='comment_post'),
]