from django.urls import path

from . import views

app_name = 'recruitment'

urlpatterns = [
    path('create/', views.create_job_posting, name='create_job_posting'),
    path('', views.job_postings, name='job_postings'),
    path('my-applications/', views.my_applications, name='my_applications'),
    path('employer/', views.ats_dashboard, name='ats_dashboard'),
    path('employer/jobs/<int:job_id>/', views.ats_job_pipeline, name='ats_job_pipeline'),
    path(
        'employer/applications/<int:application_id>/',
        views.ats_application_detail,
        name='ats_application_detail',
    ),
    path(
        'employer/applications/<int:application_id>/status/',
        views.update_application_status,
        name='update_application_status',
    ),
    path(
        'employer/applications/<int:application_id>/notes/',
        views.add_application_note,
        name='add_application_note',
    ),
    path(
        'employer/applications/bulk-status/',
        views.bulk_update_application_status,
        name='bulk_update_application_status',
    ),
    path(
        'employer/jobs/<int:job_id>/export-csv/',
        views.export_applications_csv,
        name='export_applications_csv',
    ),
    path('<int:job_posting_id>/apply/', views.apply_for_job, name='apply_for_job'),
]
