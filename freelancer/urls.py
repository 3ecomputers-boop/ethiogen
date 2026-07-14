
from django.conf.urls.static import static
from django.urls import path
from . import views

urlpatterns = [
    path('profile/', views.freelancer_profile, name='freelancer_profile'),
    path('create_job/', views.create_job_posting, name='create_job'),
    path('jobs/<int:job_id>/', views.job_detail, name='job_detail'),
    path('jobs/<int:job_id>/bid/', views.place_bid, name='place_bid'),
        path('freelancingjobs/', views.list_freelancing_job, name='freelancingjobs'),

]

