# admin.py
from django.contrib.admin import AdminSite

class CustomAdminSite(AdminSite):
    index_template = 'admin/staff_dashboard.html'

admin_site = CustomAdminSite(name='myadmin')