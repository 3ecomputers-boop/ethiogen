from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_job_posting, name='create_job_posting'),
    path('', views.job_postings, name='job_postings'),
    path('<int:job_posting_id>/apply/', views.apply_for_job, name='apply_for_job'),
]