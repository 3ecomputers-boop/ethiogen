from django.shortcuts import render

# Create your views here.
def Employer(request):
    return render(request, 'employers/employers.html')