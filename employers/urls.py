from django.urls import path
from . import views

from django.urls import path, include

urlpatterns = [
    
    path('', include('jobs.urls')), 
    path('accounts/', include('accounts.urls')), 
    path('employers/', views.Employer,name='employers'), 
]