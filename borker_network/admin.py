from django.contrib import admin
from .models import Broker, Deal, Payout, Task

admin.site.register(Broker)
class BrokerAdmin(admin.ModelAdmin):
    list_display = ('user','phone') 
   

admin.site.register(Deal)
admin.site.register(Payout)
admin.site.register(Task)