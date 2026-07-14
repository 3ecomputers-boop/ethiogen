from django import forms
from .models import FreelancerProfile, JobPosting, Bid

class FreelancerProfileForm(forms.ModelForm):
    class Meta:
        model = FreelancerProfile
        fields = ['skills', 'bio', 'portfolio_url']

class JobPostingForm(forms.ModelForm):
    class Meta:
        model = JobPosting
        fields = ['title', 'description', 'budget', 'deadline']

class BidForm(forms.ModelForm):
    class Meta:
        model = Bid
        fields = ['amount', 'proposal']
