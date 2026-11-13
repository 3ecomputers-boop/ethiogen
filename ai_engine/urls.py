from django.urls import path

from . import views

app_name = 'ai_engine'

urlpatterns = [
    path('', views.job_matches, name='job_matches'),
    path('candidates/', views.employer_candidates_index, name='employer_candidates'),
    path('jobs/<int:job_id>/candidates/', views.job_candidates, name='job_candidates'),
    path('api/jobs/', views.api_job_matches, name='api_job_matches'),
    path(
        'api/jobs/<int:job_id>/candidates/',
        views.api_job_candidates,
        name='api_job_candidates',
    ),
]
