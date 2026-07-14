
from django.contrib import admin
from django.urls import path,include
from jobs.views import staff_dashboard  # import the view

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/dashboard/', staff_dashboard, name='staff_dashboard'),
    path('admin/', admin.site.urls),
    path('',include('jobs.urls')),
    path('', include('accounts.urls')), 
    path('',include('freelancer.urls')),
     path('',include('employers.urls')),
    
       path('recruitment/', include('recruitment.urls')), 
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)