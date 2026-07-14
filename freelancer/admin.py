from django.contrib import admin
from .models import FreelancerProfile,JobPosting,Bid,Skill

admin.site.register(FreelancerProfile)

admin.site.register(JobPosting)

admin.site.register(Bid)

admin.site.register(Skill)
# Register your models here.
