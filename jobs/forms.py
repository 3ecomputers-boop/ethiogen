from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()
from .models import JobSeekerProfile, Job, ClientProfile, Message, Review

# Helper function to apply Tailwind CSS classes to form fields automatically
def add_tailwind_classes(fields):
    css_class = 'w-full p-3 bg-slate-50 dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none transition-all dark:text-white'
    for field_name, field in fields.items():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs['class'] = 'w-5 h-5 text-brand-600 border-slate-300 rounded focus:ring-brand-500'
        elif isinstance(field.widget, forms.Select):
            field.widget.attrs['class'] = css_class
        elif isinstance(field.widget, forms.Textarea):
            field.widget.attrs['class'] = css_class
            field.widget.attrs.setdefault('rows', 4)
        elif isinstance(field.widget, forms.HiddenInput):
            pass # Don't add classes to hidden inputs
        else:
            field.widget.attrs['class'] = css_class

# ============================================================================
# 1. REGISTRATION FORM
# ============================================================================
class JobSeekerRegistrationForm(UserCreationForm):
    """Custom registration form for job seekers."""
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


# ============================================================================
# 2. PROFILE & JOB FORMS
# ============================================================================
class JobSeekerProfileForm(forms.ModelForm):
    class Meta:
        model = JobSeekerProfile
        # Excludes auto-generated or system-managed fields
        exclude = ['user', 'is_active', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


class JobForm(forms.ModelForm):
    class Meta:
        model = Job
        exclude = ['posted_date', 'client', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = ClientProfile
        exclude = ['user', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


class JobRequestForm(forms.ModelForm):
    """Used by clients to post new job requests."""
    class Meta:
        model = Job  # Assumes JobRequest uses the Job model based on your views.py
        exclude = ['posted_date', 'client', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


# ============================================================================
# 3. MESSAGING & REVIEW FORMS
# ============================================================================
class MessageForm(forms.ModelForm):
    # Hidden field to pass the recipient's ID in the background
    recipient_id = forms.IntegerField(widget=forms.HiddenInput())
    
    class Meta:
        model = Message
        fields = ['recipient_id', 'message']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        # Excludes relational fields that are set in the view (job, client, service_provider)
        exclude = ['job', 'client', 'service_provider', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()
from django_countries.widgets import CountrySelectWidget

from .models import JobSeekerProfile, Job, ClientProfile, Message, Review


def add_tailwind_classes(fields):
    """Apply Tailwind CSS classes to form fields."""
    css_class = 'w-full p-3 bg-slate-50 dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none transition-all dark:text-white'
    for field_name, field in fields.items():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs['class'] = 'w-5 h-5 text-brand-600 border-slate-300 rounded focus:ring-brand-500'
        elif isinstance(field.widget, forms.Select):
            field.widget.attrs['class'] = css_class
        elif isinstance(field.widget, forms.Textarea):
            field.widget.attrs['class'] = css_class
            field.widget.attrs.setdefault('rows', 4)
        elif isinstance(field.widget, forms.HiddenInput):
            pass
        else:
            field.widget.attrs['class'] = css_class


class JobSeekerRegistrationForm(UserCreationForm):
    """Registration form with CAPTCHA and country selection."""
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    country = forms.CharField(required=True, widget=forms.Select(
        attrs={'class': 'w-full p-3 bg-slate-50 dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none transition-all dark:text-white'}
    ))
    phone_number = forms.CharField(required=False, max_length=20)
    
    # Human verification - reCAPTCHA v2
   

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)
        
        # Populate country choices from django-countries
        from django_countries import countries
        self.fields['country'].widget.choices = [('', 'Select your country')] + list(countries)


class JobSeekerProfileForm(forms.ModelForm):
    class Meta:
        model = JobSeekerProfile
        exclude = ['user', 'is_active', 'created_at', 'updated_at', 
                   'otp_code', 'otp_created_at', 'otp_attempts', 'otp_expires_at',
                   'is_verified', 'email_verified', 'phone_verified']
        widgets = {
            'country': CountrySelectWidget(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


class OTPVerificationForm(forms.Form):
    """Form for OTP verification."""
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'text-center text-3xl font-bold tracking-widest w-full p-4 bg-slate-50 dark:bg-slate-800 rounded-xl border-2 border-slate-200 dark:border-slate-700 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none transition-all dark:text-white',
            'placeholder': '000000',
            'maxlength': '6',
            'autocomplete': 'one-time-code',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
        })
    )


# Keep other forms unchanged
class JobForm(forms.ModelForm):
    class Meta:
        model = Job
        exclude = ['posted_date', 'client', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = ClientProfile
        exclude = ['user', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


class JobRequestForm(forms.ModelForm):
    class Meta:
        model = Job
        exclude = ['posted_date', 'client', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


class MessageForm(forms.ModelForm):
    recipient_id = forms.IntegerField(widget=forms.HiddenInput())
    
    class Meta:
        model = Message
        fields = ['recipient_id', 'message']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        exclude = ['job', 'client', 'service_provider', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_tailwind_classes(self.fields)