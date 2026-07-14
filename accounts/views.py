"""
Accounts App Views
Handles user registration, authentication, logout, and role-based routing.
"""

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import RegistrationForm


# ============================================================================
# REGISTRATION
# ============================================================================

def register(request):
    """
    Create a new user account and redirect to login.

    Preserves the ``next`` query parameter so the user is sent to their
    intended destination after authenticating.
    """
    next_url = request.GET.get('next')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                f'Account created for {user.username}! Please log in.',
            )

            login_url = reverse('accounts:login')
            if next_url:
                return redirect(f'{login_url}?next={next_url}')
            return redirect('accounts:login')

    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


# ============================================================================
# AUTHENTICATION
# ============================================================================

def login_view(request):
    """
    Authenticate a user and redirect to the appropriate dashboard.

    Redirect priority:
        1. ``next`` parameter  – if present and safely rooted at ``/``
        2. Role-based routing  – staff → construction, seeker → dashboard,
                                  client → employer, else → profile setup
        3. ``LOGIN_REDIRECT_URL`` from settings (implicit Django fallback)
    """
    next_url = request.GET.get('next') or request.POST.get('next')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')

            # --- Priority 1: explicit 'next' (must be a safe relative path) ---
            if next_url:
                if next_url.startswith('/'):
                    return HttpResponseRedirect(next_url)
                messages.warning(
                    request,
                    'Unsafe redirect URL detected. Using default destination.',
                )

            # --- Priority 2: role-based routing ---
            destination = _resolve_dashboard(user)
            return redirect(destination)

        # --- Invalid credentials ---
        messages.error(request, 'Invalid username or password.')

    else:
        form = AuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form, 'next': next_url})


def _resolve_dashboard(user):
    """
    Determine the correct dashboard URL for a given user based on their role.

    Returns a Django-resolvable URL name string (namespaced).
    """
    # Staff / Admin → Construction Workforce Dashboard
    if user.is_staff:
        return 'jobs:construction_dashboard'

    # Job Seeker → OTP verification or personal dashboard
    if hasattr(user, 'job_seeker_profile'):
        profile = user.job_seeker_profile
        if not profile.is_verified:
            return 'jobs:verify_otp'
        return 'jobs:job_seeker_dashboard'

    # Client / Employer → Shortlist & Checkout Dashboard (fixed underscore)
    if hasattr(user, 'client_profile'):
        return 'jobs:employer_dashboard'   # ✅ correct name

    # No profile yet → guide them to create one
    return 'jobs:client_profile'


# ============================================================================
# LOGOUT
# ============================================================================

def logout_view(request):
    """
    End the current session and redirect to the home page.

    Accepts an optional ``next`` parameter for custom post-logout destinations.
    """
    logout(request)
    messages.info(request, 'You have been logged out successfully.')

    next_url = request.GET.get('next')
    if next_url and next_url.startswith('/'):
        return HttpResponseRedirect(next_url)

    return redirect('jobs:home')


# ============================================================================
# ACCOUNT HOME
# ============================================================================

def home(request):
    """
    Simple authenticated landing page for the accounts app.

    Unauthenticated visitors are redirected to login with a warning message.
    """
    if request.user.is_authenticated:
        return render(request, 'home.html', {
            'username': request.user.username,
        })

    messages.warning(request, 'Please log in to access this page.')
    return redirect('accounts:login')