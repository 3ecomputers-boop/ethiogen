from django import forms

from jobs.models import Job

from .models import Application


class JobPostingForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = [
            'title',
            'company_name',
            'description',
            'category',
            'employment_type',
            'experience_required',
            'required_skills',
            'location',
            'preferred_schedule',
            'salary',
            'budget',
            'responsibilities',
            'description_of_work',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'responsibilities': forms.Textarea(attrs={'rows': 4}),
            'description_of_work': forms.Textarea(attrs={'rows': 4}),
        }


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ['cover_letter', 'resume']
        widgets = {
            'cover_letter': forms.Textarea(attrs={'rows': 6}),
        }


class ApplicationStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Application.STATUS_CHOICES)


class ApplicationNoteForm(forms.Form):
    note = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3}),
    )
