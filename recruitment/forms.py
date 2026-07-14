from django import forms
from jobs.models import Job
from .models import Application


class JobPostingForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = "__all__"


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ['cover_letter', 'resume']