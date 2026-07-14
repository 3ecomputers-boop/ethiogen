from django import forms
from .models import Employer

class EmployerForm(forms.ModelForm):
    class Meta:
        model = Employer
        fields = ['company_name', 'website', 'description']

# employers/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Employer
from .forms import EmployerForm

@login_required
def employer_profile(request):
    try:
        employer = request.user.employer 
    except Employer.DoesNotExist:
        employer = None

    if request.method == 'POST':
        form = EmployerForm(request.POST, instance=employer)
        if form.is_valid():
            employer = form.save(commit=False)
            employer.user = request.user 
            employer.save()
            return redirect('employer_profile')
    else:
        form = EmployerForm(instance=employer)

    context = {'form': form}
    return render(request, 'employers/employer_profile.html', context)