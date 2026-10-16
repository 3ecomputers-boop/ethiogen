"""
Jobs App Views
Handles job seeker registration, OTP verification, dashboard, marketplace functionality,
talent management, and API endpoints for the Ethiogen platform.
"""

# ============================================================================
# STANDARD LIBRARY IMPORTS
# ============================================================================
import json
import logging
import base64
import os
import urllib.request
from datetime import datetime, timedelta
from io import BytesIO

# ============================================================================
# DJANGO IMPORTS
# ============================================================================
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.images import ImageFile
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import activate
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

# ============================================================================
# LOCAL IMPORTS
# ============================================================================
from .forms import (
    ClientProfileForm,
    JobForm,
    JobRequestForm,
    JobSeekerProfileForm,
    JobSeekerRegistrationForm,
    MessageForm,
    OTPVerificationForm,
    ReviewForm,
)
from .models import (
    ClientProfile,
    HireRequest,
    Job,
    JobCategory,
    JobSeekerProfile,
    Message,
    PostNeedRequest,
    Profession,
    Review,
    Talent,
    TalentAccess,
)

# Published construction rate card (single source of truth: jobs/rates.py)
from .rates import MARKUP, rate_card

# ============================================================================
# CONFIGURATION
# ============================================================================
logger = logging.getLogger(__name__)
User = get_user_model()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# jobs/views.py
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from telegram import Update
def some_view(request):
    from .bot import application   # lazy import
    # now use application

@csrf_exempt
async def telegram_webhook(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            update = Update.de_json(data, app.bot)
            await app.process_update(update)
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse({"error": "Only POST allowed"}, status=405)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_image_url(image_field):
    """
    Safely get the URL from an ImageField or string URL.
    Returns the URL if available, otherwise an empty string.
    Does NOT check file existence on disk – that responsibility is left to
    the template (e.g., onerror fallback).
    """
    if not image_field:
        return ''

    # If it's a Django FileField with a `url` attribute
    if hasattr(image_field, 'url'):
        try:
            return image_field.url
        except (ValueError, AttributeError, Exception) as e:
            logger.warning(f"Could not get image URL: {e}")
            return ''

    # If it's already a string (e.g., a URL stored as text)
    if isinstance(image_field, str):
        stripped = image_field.strip()
        if stripped and (stripped.startswith('/') or stripped.startswith('http')):
            return stripped

    return ''


def save_image_from_url(talent, url):
    """
    Download an image from a URL and save it to the talent's ImageField.
    
    Args:
        talent: Talent instance
        url: str, the image URL
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not url or not url.startswith(('http://', 'https://')):
        return False
    
    try:
        # Download the image
        with urllib.request.urlopen(url, timeout=10) as response:
            content = response.read()
            # Get file extension from URL or content-type
            content_type = response.info().get_content_type()
            ext = content_type.split('/')[-1] if content_type else 'jpg'
            if ext not in ['jpeg', 'jpg', 'png', 'gif', 'webp']:
                ext = 'jpg'
            
            # Create a ContentFile and assign to image field
            file_name = f"talent_{talent.id}_url.{ext}"
            talent.image.save(file_name, ContentFile(content), save=False)
            logger.info(f"Downloaded image from URL for talent {talent.id}")
            return True
    except Exception as e:
        logger.error(f"Failed to download image from URL for talent {talent.id}: {str(e)}")
        return False


def _timesince(dt):
    """Simple timesince helper returning human-readable time difference."""
    diff = timezone.now() - dt
    if diff.days > 365:
        return f"{diff.days // 365} year(s) ago"
    elif diff.days > 30:
        return f"{diff.days // 30} month(s) ago"
    elif diff.days > 0:
        return f"{diff.days} day(s) ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} hour(s) ago"
    else:
        return "just now"


def _parse_experience(exp_str):
    """Convert experience range string to integer years."""
    mapping = {
        '0-1': 1,
        '1-3': 2,
        '3-5': 4,
        '5-10': 7,
        '10+': 12,
    }
    return mapping.get(str(exp_str), 1)


def _send_otp_email(email, first_name, otp):
    """
    Send OTP verification email to user.
    
    Args:
        email: Recipient email address
        first_name: User's first name
        otp: OTP code to send
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    subject = 'Your Ethiogen Verification Code'

    plain_message = f"""
Hi {first_name},

Welcome to Ethiogen! Your verification code is:

    {otp}

This code will expire in 10 minutes.

If you didn't request this, please ignore this email.

Best regards,
The Ethiogen Team
    """

    html_message = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #f97316, #f59e0b); padding: 30px; text-align: center;">
            <h1 style="color: white; margin: 0;">Ethiogen</h1>
        </div>
        <div style="padding: 30px; background: #f8fafc;">
            <h2 style="color: #0f172a;">Hi {first_name},</h2>
            <p style="color: #475569;">Welcome to Ethiogen! Use this code to verify your email:</p>
            <div style="background: white; padding: 20px; text-align: center; border-radius: 12px; margin: 20px 0;">
                <h1 style="color: #f97316; font-size: 48px; letter-spacing: 8px; margin: 0;">{otp}</h1>
            </div>
            <p style="color: #64748b; font-size: 14px;">⏰ This code expires in 10 minutes.</p>
            <p style="color: #94a3b8; font-size: 12px;">If you didn't request this, please ignore this email.</p>
        </div>
    </div>
    """

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"OTP email sent successfully to {email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {str(e)}")
        # Fallback: Print OTP to console in development
        if settings.DEBUG:
            print(f"\n{'='*60}")
            print(f"OTP for {email}: {otp}")
            print(f"{'='*60}\n")
        return False


def _calculate_profile_completion(profile):
    """
    Calculate profile completion percentage.
    
    Args:
        profile: JobSeekerProfile instance
    
    Returns:
        int: Completion percentage (0-100)
    """
    fields_to_check = [
        profile.title,
        profile.bio,
        profile.country,
        profile.city,
        profile.hourly_rate,
        profile.years_of_experience,
        profile.skills,
        profile.profile_picture,
    ]

    filled_count = sum(1 for field in fields_to_check if field)
    total_count = len(fields_to_check)

    if total_count == 0:
        return 0

    return int((filled_count / total_count) * 100)


# ============================================================================
# REGISTRATION & OTP VERIFICATION
# ============================================================================

def job_seeker_register(request):
    """
    Register a new job seeker account and send OTP verification email.
    Returns JSON response with success/error status.
    """
    if request.method != 'POST':
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid request method'},
            status=405
        )

    form = JobSeekerRegistrationForm(request.POST)

    if not form.is_valid():
        errors = {
            field: [str(error) for error in error_list]
            for field, error_list in form.errors.items()
        }
        return JsonResponse({'status': 'error', 'errors': errors}, status=400)

    try:
        # Create inactive user (requires OTP verification)
        user = form.save(commit=False)
        user.is_active = False
        user.save()

        # Create job seeker profile
        profile = JobSeekerProfile.objects.create(
            user=user,
            country=form.cleaned_data.get('country', ''),
            phone_number=form.cleaned_data.get('phone_number', ''),
            is_verified=False,
            email_verified=False,
        )

        # Generate and send OTP
        otp = profile.generate_otp()
        email_sent = _send_otp_email(user.email, user.first_name, otp)

        # Store user ID in session for OTP verification
        request.session['pending_user_id'] = user.id

        message = 'Account created! Check your email for OTP.'
        if not email_sent:
            message += ' (Email delivery failed - check console for OTP)'

        return JsonResponse({
            'status': 'success',
            'message': message,
            'redirect': '/verify-otp/'
        })

    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        return JsonResponse(
            {'status': 'error', 'message': 'Registration failed. Please try again.'},
            status=500
        )


def verify_otp_view(request):
    """
    OTP verification page.
    Handles both regular form submission and AJAX requests.
    """
    pending_user_id = request.session.get('pending_user_id')

    if not pending_user_id:
        return redirect('jobs:home')

    try:
        profile = JobSeekerProfile.objects.select_related('user').get(user_id=pending_user_id)
    except JobSeekerProfile.DoesNotExist:
        logger.warning(f"Pending user {pending_user_id} not found")
        return redirect('jobs:home')

    # Redirect if already verified
    if profile.is_verified:
        return redirect('jobs:job_seeker_dashboard')

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = OTPVerificationForm(request.POST)

        if form.is_valid():
            otp_code = form.cleaned_data['otp']
            success, message = profile.verify_otp(otp_code)

            if success:
                # Log user in automatically
                login(request, profile.user)

                # Clear session
                if 'pending_user_id' in request.session:
                    del request.session['pending_user_id']

                logger.info(f"User {profile.user.username} verified successfully")

                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': message,
                        'redirect': '/dashboard/'
                    })
                return redirect('jobs:job_seeker_dashboard')

            else:
                logger.warning(f"OTP verification failed for user {profile.user.username}: {message}")
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': message}, status=400)

                return render(request, 'verify_otp.html', {
                    'form': form,
                    'error': message,
                    'email': profile.user.email
                })
    else:
        form = OTPVerificationForm()

    return render(request, 'verify_otp.html', {
        'form': form,
        'email': profile.user.email
    })


@require_POST
def resend_otp_view(request):
    """Resend OTP via AJAX."""
    pending_user_id = request.session.get('pending_user_id')

    if not pending_user_id:
        return JsonResponse(
            {'status': 'error', 'message': 'Session expired. Please register again.'},
            status=400
        )

    try:
        profile = JobSeekerProfile.objects.select_related('user').get(user_id=pending_user_id)
        otp = profile.generate_otp()
        email_sent = _send_otp_email(profile.user.email, profile.user.first_name, otp)

        if email_sent:
            return JsonResponse({
                'status': 'success',
                'message': 'New OTP sent to your email!'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Failed to send email. Check console for OTP.'
            }, status=500)

    except JobSeekerProfile.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Profile not found'},
            status=404
        )
    except Exception as e:
        logger.error(f"Error resending OTP: {str(e)}", exc_info=True)
        return JsonResponse(
            {'status': 'error', 'message': 'Failed to resend OTP. Please try again.'},
            status=500
        )


# ============================================================================
# JOB SEEKER DASHBOARD
# ============================================================================

@login_required
def job_seeker_dashboard(request):
    """
    Personal dashboard for verified job seekers.
    Redirects to OTP verification if not verified.
    """
    try:
        profile = request.user.job_seeker_profile
    except JobSeekerProfile.DoesNotExist:
        return redirect('jobs:create_job_seeker_profile')

    # Redirect to OTP if not verified
    if not profile.is_verified:
        request.session['pending_user_id'] = request.user.id
        return redirect('jobs:verify_otp')

    context = {
        'profile': profile,
        'total_applications': 0,
        'saved_jobs': 0,
        'profile_completion': _calculate_profile_completion(profile),
    }

    return render(request, 'job_seeker_dashboard.html', context)


# ============================================================================
# PUBLIC PAGES
# ============================================================================

def home(request):
    """
    Main marketplace homepage.
    Displays all talents with session data for cart/wishlist/compare.
    """
    talents_qs = Talent.objects.all().order_by('-rating', '-reviews')

    talents_list = [
        {
            'id': t.id,
            'name': t.name,
            'role': t.role,
            'location': t.location,
            'price': t.price,
            'rating': t.rating,
            'reviews': t.reviews,
            'skills': t.skills,
            'image': get_image_url(t.image),
            'category': t.category,
            'verified': t.verified,
            'top': t.top,
            'duration': t.duration,
            'type': t.type,
            'bio': t.bio,
            'tier': t.tier,
            'sub_ratings': t.sub_ratings,
            'portfolio': t.portfolio,
            'availability': t.availability,
            'radius': t.radius,
            'remote': t.remote,
            'experience': t.experience,
            'education': t.education,
            'languages': t.languages,
            'available_from': t.available_from,
            'created_at': t.created_at.strftime('%Y-%m-%d') if t.created_at else None,
            'certifications': t.certifications,
        }
        for t in talents_qs
    ]

    context = {
        'talents_json': json.dumps(talents_list),
        'initial_cart': json.dumps(request.session.get('cart', [])),
        'initial_wishlist': json.dumps(request.session.get('wishlist', [])),
        'initial_compare': json.dumps(request.session.get('compare', [])),
        'initial_recent': json.dumps(request.session.get('recently_viewed', [])),
        # Published construction rate card. Single source of truth in
        # jobs.rates, so the card and the listing prices cannot drift apart.
        'rate_card': rate_card(),
        'markup_percent': round((MARKUP - 1) * 100),
    }

    return render(request, 'home.html', context)


def change_language(request, language):
    """Change session language and redirect back."""
    if language not in dict(settings.LANGUAGES):
        language = settings.LANGUAGE_CODE

    translation.activate(language)
    request.session[translation.LANGUAGE_SESSION_KEY] = language
    request.session['django_language'] = language

    return redirect(request.META.get('HTTP_REFERER', '/'))


def browse_job_seekers(request):
    """Browse all active and verified job seekers."""
    job_seekers = JobSeekerProfile.objects.filter(
        is_active=True,
        is_verified=True
    ).select_related('user')

    categories = JobCategory.objects.all()
    professions = Profession.objects.all()

    return render(request, 'browse_job_seekers.html', {
        'job_seekers': job_seekers,
        'categories': categories,
        'professions': professions,
    })


# ============================================================================
# JOB SEEKER PROFILE MANAGEMENT
# ============================================================================

@login_required
def create_job_seeker_profile(request):
    """Create or update job seeker profile."""
    try:
        profile = request.user.job_seeker_profile
    except JobSeekerProfile.DoesNotExist:
        profile = None

    if request.method == 'POST':
        post_data = request.POST.copy()

        # Convert comma-separated skills string to valid JSON
        raw_skills = post_data.get('skills', '')
        if raw_skills:
            skills_list = [s.strip() for s in raw_skills.split(',') if s.strip()]
            post_data['skills'] = json.dumps(skills_list)
        else:
            post_data['skills'] = json.dumps([])

        form = JobSeekerProfileForm(post_data, request.FILES, instance=profile)

        if form.is_valid():
            profile = form.save(commit=False)
            if not profile.user_id:
                profile.user = request.user
            profile.save()

            logger.info(f"Profile updated for user {request.user.username}")
            return redirect('jobs:job_seeker_dashboard')
        else:
            logger.error(f"Profile creation failed: {form.errors}")
    else:
        form = JobSeekerProfileForm(instance=profile)

    return render(request, 'create_job_seeker_profile.html', {'form': form})


@login_required
def view_job_seeker_profile(request, pk):
    """View a job seeker's public profile."""
    profile = get_object_or_404(
        JobSeekerProfile.objects.select_related('user'),
        pk=pk
    )
    return render(request, 'view_job_seeker_profile.html', {'profile': profile})


# ============================================================================
# JOB MANAGEMENT
# ============================================================================

@login_required
def add_job(request):
    """Create a new job posting. Sets status to Pending Admin Approval."""
    if request.method == 'POST':
        form = JobForm(request.POST)

        if form.is_valid():
            job = form.save(commit=False)
            job.client = request.user.client_profile
            job.is_approved = False
            job.save()

            logger.info(f"New job posted by {request.user.username}. Awaiting admin approval.")
            messages.success(request, 'Job submitted! It is now pending admin approval.')
            return redirect('jobs:client_dashboard')
    else:
        form = JobForm()

    return render(request, 'add_job.html', {'form': form})


def list_jobs(request):
    """
    List and filter jobs with pagination.
    Supports filtering by query, category, job type, location,
    experience range, and date range.
    """
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    job_type = request.GET.get('job_type', '').strip()
    location = request.GET.get('location', '').strip()
    min_experience = request.GET.get('min_experience', 0)
    max_experience = request.GET.get('max_experience', 100)
    date_range = request.GET.get('posted_within', 30)

    jobs = Job.objects.all()

    if query:
        jobs = jobs.filter(
            Q(title__icontains=query) | Q(company_name__icontains=query)
        )

    if category:
        jobs = jobs.filter(category__icontains=category)

    if job_type:
        jobs = jobs.filter(employment_type=job_type)

    if location:
        jobs = jobs.filter(location__icontains=location)

    if min_experience and max_experience:
        try:
            jobs = jobs.filter(
                experience_required__gte=int(min_experience),
                experience_required__lte=int(max_experience)
            )
        except (ValueError, TypeError):
            pass

    if date_range:
        try:
            days = int(date_range)
            cutoff_date = timezone.now() - timedelta(days=days)
            jobs = jobs.filter(posted_date__gte=cutoff_date)
        except (ValueError, TypeError):
            pass

    jobs = jobs.order_by('-posted_date')

    paginator = Paginator(jobs, 10)
    page_number = request.GET.get('page')
    page_jobs = paginator.get_page(page_number)

    return render(request, 'list_jobs.html', {'jobs': page_jobs})


@login_required
def job_details(request, job_id):
    """View job details and send messages to job poster."""
    job = get_object_or_404(Job, pk=job_id)

    if request.method == "POST":
        form = MessageForm(request.POST)

        if form.is_valid():
            recipient_id = form.cleaned_data['recipient_id']

            try:
                recipient = User.objects.get(pk=recipient_id)
            except User.DoesNotExist:
                raise Http404("Recipient does not exist")

            if recipient == request.user:
                return render(request, 'job_details.html', {
                    'job': job,
                    'form': form,
                    'error': 'You cannot send a message to yourself.'
                })

            message = Message.objects.create(
                sender=request.user,
                recipient=recipient,
                message=form.cleaned_data['message']
            )

            logger.info(f"Message sent from {request.user.username} to {recipient.username}")
            return redirect('jobs:job_details', job_id=job_id)
    else:
        form = MessageForm()

    return render(request, 'job_details.html', {'job': job, 'form': form})


# ============================================================================
# CLIENT MANAGEMENT
# ============================================================================

@login_required
def client_profile(request):
    """Create or update client profile. Sets verified to False for Admin approval."""
    try:
        profile = request.user.client_profile
    except ClientProfile.DoesNotExist:
        profile = None

    if request.method == 'POST':
        form = ClientProfileForm(request.POST, request.FILES, instance=profile)

        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.is_verified = False
            profile.save()

            logger.info(f"Company profile updated by {request.user.username}. Awaiting admin verification.")
            messages.success(request, 'Profile saved! It is pending admin verification.')
            return redirect('jobs:client_dashboard')
    else:
        form = ClientProfileForm(instance=profile)

    return render(request, 'client_profile.html', {'form': form})


@login_required
def client_dashboard(request):
    """Display client's posted jobs."""
    try:
        jobs = request.user.client_profile.jobs.all()
    except ClientProfile.DoesNotExist:
        jobs = Job.objects.none()

    return render(request, 'client_dashboard.html', {'jobs': jobs})


@login_required
def create_job_request(request):
    """Create a new job request as a client."""
    try:
        client_profile = request.user.client_profile
    except ClientProfile.DoesNotExist:
        return redirect('jobs:client_profile')

    if request.method == 'POST':
        form = JobRequestForm(request.POST)

        if form.is_valid():
            job = form.save(commit=False)
            job.client = client_profile
            job.save()
            form.save_m2m()

            logger.info(f"Job request created by client {request.user.username}")
            return redirect('jobs:client_dashboard')
    else:
        form = JobRequestForm()

    return render(request, 'create_job_request.html', {'form': form})


# ============================================================================
# REVIEWS
# ============================================================================

@login_required
def create_review(request, job_id, service_provider_id):
    """Create a review for a service provider."""
    job = get_object_or_404(Job, pk=job_id)
    service_provider = get_object_or_404(JobSeekerProfile, pk=service_provider_id)

    try:
        client_profile = request.user.client_profile
    except ClientProfile.DoesNotExist:
        return redirect('jobs:client_profile')

    if request.method == "POST":
        form = ReviewForm(request.POST)

        if form.is_valid():
            review = form.save(commit=False)
            review.job = job
            review.client = client_profile
            review.service_provider = service_provider
            review.save()

            logger.info(
                f"Review created by {request.user.username} for "
                f"{service_provider.user.username} on job {job.title}"
            )
            return redirect('jobs:job_details', job_id=job_id)
    else:
        form = ReviewForm()

    return render(request, 'create_review.html', {
        'form': form,
        'job': job,
        'service_provider': service_provider
    })


# ============================================================================
# AJAX ENDPOINTS
# ============================================================================

@require_POST
def submit_hire_request(request):
    """Handle hire request form submission via AJAX."""
    try:
        talent_id = request.POST.get('talent_id')
        talent = None

        if talent_id:
            try:
                talent = Talent.objects.get(id=talent_id)
            except Talent.DoesNotExist:
                pass

        HireRequest.objects.create(
            talent=talent,
            company_name=request.POST.get('company_name', ''),
            email=request.POST.get('email', ''),
            budget=request.POST.get('budget', 0),
            details=request.POST.get('details', ''),
        )

        talent_name = talent.name if talent else 'Unknown'
        logger.info(f"Hire request submitted for talent: {talent_name}")

        return JsonResponse({
            'status': 'success',
            'message': f'Request sent for {talent_name}!'
        })

    except Exception as e:
        logger.error(f"Error submitting hire request: {str(e)}", exc_info=True)
        return JsonResponse(
            {'status': 'error', 'message': 'Failed to submit request. Please try again.'},
            status=500
        )


@require_POST
def submit_post_need(request):
    """Handle post-a-need form submission via AJAX."""
    try:
        PostNeedRequest.objects.create(
            job_title=request.POST.get('job_title', ''),
            description=request.POST.get('description', ''),
            budget=request.POST.get('budget', 0),
        )

        logger.info("New job need posted")

        return JsonResponse({
            'status': 'success',
            'message': 'Need posted successfully!'
        })

    except Exception as e:
        logger.error(f"Error posting need: {str(e)}", exc_info=True)
        return JsonResponse(
            {'status': 'error', 'message': 'Failed to post need. Please try again.'},
            status=500
        )


@require_POST
def update_session_state(request):
    """Sync cart/wishlist/compare state from JavaScript to Django sessions."""
    try:
        data = json.loads(request.body)

        if 'cart' in data:
            request.session['cart'] = data['cart']
        if 'wishlist' in data:
            request.session['wishlist'] = data['wishlist']
        if 'compare' in data:
            request.session['compare'] = data['compare']
        if 'recently_viewed' in data:
            request.session['recently_viewed'] = data['recently_viewed']

        return JsonResponse({'status': 'success'})

    except json.JSONDecodeError:
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid JSON data'},
            status=400
        )
    except Exception as e:
        logger.error(f"Error updating session state: {str(e)}", exc_info=True)
        return JsonResponse(
            {'status': 'error', 'message': 'Failed to update session'},
            status=500
        )


# ============================================================================
# LANDING PAGES & DASHBOARDS
# ============================================================================

def construction_workforce_page(request):
    """Render the Construction Workforce landing page."""
    return render(request, 'construction_workforce.html')


def business_consultancy_page(request):
    """Render the Business Consultancy landing page."""
    return render(request, 'business_consultancy.html')


@login_required
def construction_dashboard(request):
    """Dashboard for Construction Workforce Management. Only accessible by staff."""
    if not request.user.is_staff:
        return redirect('jobs:home')

    context = {
        'page_title': 'Construction Workforce Management',
    }
    return render(request, 'jobs/construction_dashboard.html', context)


# ============================================================================
# EMPLOYER DASHBOARD & CHECKOUT
# ============================================================================

@login_required
def employer_dashboard(request):
    """Employer dashboard showing shortlisted talents with payment status."""
    try:
        employer = request.user.client_profile
    except ClientProfile.DoesNotExist:
        messages.warning(request, 'Please complete your company profile first.')
        return redirect('jobs:client_profile')

    cart = request.session.get('cart', [])
    cart_workers = []
    paid_status = {}

    if cart:
        cart_workers = list(Talent.objects.filter(id__in=cart))
        worker_dict = {w.id: w for w in cart_workers}
        cart_workers = [worker_dict[id] for id in cart if id in worker_dict]

        access_records = TalentAccess.objects.filter(employer=employer, talent__in=cart_workers)
        access_map = {acc.talent_id: acc for acc in access_records}

        for worker in cart_workers:
            acc = access_map.get(worker.id)
            paid_status[worker.id] = acc.paid if acc else False

    context = {
        'cart': cart,
        'cart_workers': cart_workers,
        'paid_status': paid_status,
    }
    return render(request, 'employer_dashboard.html', context)


@login_required
def checkout(request):
    """Checkout process: creates TalentAccess records for all cart items (unpaid)."""
    cart = request.session.get('cart', [])
    if not cart:
        messages.warning(request, 'Your shortlist is empty.')
        return redirect('jobs:employer_dashboard')

    try:
        employer = request.user.client_profile
    except ClientProfile.DoesNotExist:
        messages.error(request, 'Please complete your company profile first.')
        return redirect('jobs:client_profile')

    for talent_id in cart:
        talent = get_object_or_404(Talent, id=talent_id)
        TalentAccess.objects.get_or_create(
            employer=employer,
            talent=talent,
            defaults={'paid': False, 'amount': talent.price}
        )

    messages.info(request, 'Your shortlist is ready. Pay to unlock contact details.')
    return redirect('jobs:employer_dashboard')


@login_required
def pay_for_contact(request, talent_id):
    """Simulate payment – mark access as paid and redirect back to dashboard."""
    talent = get_object_or_404(Talent, id=talent_id)

    try:
        employer = request.user.client_profile
    except ClientProfile.DoesNotExist:
        messages.error(request, 'Please complete your company profile first.')
        return redirect('jobs:client_profile')

    access, created = TalentAccess.objects.get_or_create(
        employer=employer,
        talent=talent,
        defaults={'paid': False, 'amount': talent.price}
    )

    access.paid = True
    access.paid_at = timezone.now()
    access.save()

    logger.info(f"Talent contact unlocked: {employer.user.username} → {talent.name}")
    messages.success(request, f'✅ Contact unlocked for {talent.name}!')

    return redirect('jobs:employer_dashboard')


# ============================================================================
# STAFF DASHBOARD & METRICS API
# ============================================================================

@staff_member_required
def staff_dashboard(request):
    """Admin dashboard with platform metrics and job seekers list."""
    context = {
        'total_users': User.objects.count(),
        'total_jobs': Job.objects.count(),
        'total_talents': Talent.objects.count(),
        'total_job_seekers': JobSeekerProfile.objects.count(),
        'total_clients': ClientProfile.objects.count(),
        'pending_jobs': Job.objects.filter(is_approved=False).count(),
        'total_hire_requests': HireRequest.objects.count(),
        'recent_users': User.objects.order_by('-date_joined')[:5],
        'recent_jobs': Job.objects.order_by('-posted_date')[:5],
        'recent_hire_requests': HireRequest.objects.order_by('-created_at')[:5],
        'new_users_this_week': User.objects.filter(
            date_joined__gte=timezone.now() - timedelta(days=7)
        ).count(),
        'jobs_this_month': Job.objects.filter(
            posted_date__year=timezone.now().year,
            posted_date__month=timezone.now().month
        ).count(),
    }
    return render(request, 'admin/staff_dashboard.html', context)


def dashboard_metrics_api(request):
    """API endpoint returning platform metrics for dashboard charts."""
    today = timezone.now()

    data = {
        "total_users": User.objects.count(),
        "total_jobs": Job.objects.count(),
        "pending_jobs": Job.objects.filter(is_approved=False).count(),
        "total_hire_requests": HireRequest.objects.count(),
        "new_users_today": User.objects.filter(date_joined__date=today.date()).count(),
        "new_users_week": User.objects.filter(date_joined__gte=today - timedelta(days=7)).count(),
        "jobs_last_7_days": [
            {
                "day": (today - timedelta(days=i)).strftime("%a"),
                "count": Job.objects.filter(
                    posted_date__date=(today - timedelta(days=i)).date()
                ).count()
            }
            for i in reversed(range(7))
        ],
    }

    return JsonResponse(data)


def dashboard_metrics(request):
    """Comprehensive dashboard metrics endpoint."""
    total_users = User.objects.count()
    job_seekers = User.objects.filter(groups__name='JobSeeker').count()
    clients = User.objects.filter(groups__name='Client').count()

    total_jobs = Job.objects.count()
    pending_jobs = Job.objects.filter(is_approved=False).count()
    total_talents = Talent.objects.count()
    total_hire_requests = HireRequest.objects.count()

    week_ago = datetime.now() - timedelta(days=7)
    new_users_this_week = User.objects.filter(date_joined__gte=week_ago).count()

    now = datetime.now()
    jobs_this_month = Job.objects.filter(
        posted_date__year=now.year,
        posted_date__month=now.month
    ).count()

    recent_users_qs = User.objects.order_by('-date_joined')[:5]
    recent_users = []
    for user in recent_users_qs:
        recent_users.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': user.get_full_name() or user.username,
            'date_joined': user.date_joined.isoformat(),
        })

    chart_data = []
    today = datetime.now().date()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = Job.objects.filter(posted_date__date=day).count()
        chart_data.append({
            'day': day.strftime('%a'),
            'count': count
        })

    data = {
        'total_users': total_users,
        'total_job_seekers': job_seekers,
        'total_clients': clients,
        'total_jobs': total_jobs,
        'pending_jobs': pending_jobs,
        'total_talents': total_talents,
        'total_hire_requests': total_hire_requests,
        'new_users_this_week': new_users_this_week,
        'jobs_this_month': jobs_this_month,
        'recent_users': recent_users,
        'jobs_last_7_days': chart_data,
    }
    return JsonResponse(data)


# ============================================================================
# ADMIN USER CREATION (No OTP Required)
# ============================================================================

@csrf_exempt
@require_POST
def add_job_seeker(request):
    """Admin endpoint to create job seeker without OTP verification."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    required = ['first_name', 'last_name', 'email', 'password', 'role']
    for field in required:
        if not data.get(field):
            return JsonResponse({'success': False, 'message': f'{field} is required'}, status=400)

    if User.objects.filter(email=data['email']).exists():
        return JsonResponse({
            'success': False,
            'message': 'A user with this email already exists.'
        }, status=400)

    try:
        validate_password(data['password'])
    except ValidationError as e:
        return JsonResponse({'success': False, 'message': ' '.join(e.messages)}, status=400)

    user = User.objects.create_user(
        username=data['email'],
        email=data['email'],
        password=data['password'],
        first_name=data['first_name'],
        last_name=data['last_name'],
    )

    group, _ = Group.objects.get_or_create(name='JobSeeker')
    user.groups.add(group)

    try:
        JobSeekerProfile.objects.create(
            user=user,
            title=data.get('role', ''),
            phone_number=data.get('phone', ''),
            bio=data.get('bio', ''),
            is_verified=True,
            email_verified=True,
            is_active=True,
        )
    except Exception as e:
        logger.warning(f"Could not create JobSeekerProfile: {e}")

    return JsonResponse({
        'success': True,
        'message': f'Job seeker {user.get_full_name()} created.',
        'user_id': user.id,
    })


# ============================================================================
# API: FETCH ALL JOB SEEKERS (for staff dashboard)
# ============================================================================

@login_required
def api_job_seekers(request):
    """Return all job seekers as JSON for the staff dashboard."""
    seekers = JobSeekerProfile.objects.select_related('user').order_by('-user__date_joined')
    
    data = []
    for s in seekers:
        data.append({
            'id': s.id,
            'first_name': s.user.first_name,
            'last_name': s.user.last_name,
            'full_name': s.user.get_full_name() or s.user.username,
            'email': s.user.email,
            'username': s.user.username,
            'title': s.title or '—',
            'phone': s.phone_number or '—',
            'country': str(s.country) if s.country else '—',
            'city': s.city or '—',
            'hourly_rate': float(s.hourly_rate) if s.hourly_rate else 0,
            'experience': s.years_of_experience,
            'skills': s.skills if isinstance(s.skills, list) else [],
            'is_verified': s.is_verified,
            'email_verified': s.email_verified,
            'is_active': s.is_active,
            'date_joined': s.user.date_joined.strftime('%Y-%m-%d'),
            'date_joined_timesince': _timesince(s.user.date_joined),
            'avatar_initial': (s.user.first_name or s.user.username or 'U')[0].upper(),
        })
    
    return JsonResponse({
        'success': True,
        'count': len(data),
        'seekers': data
    })


# ============================================================================
# API: FETCH TALENTS (for front page marketplace)
# ============================================================================

from django.http import JsonResponse

def api_talents(request):
    """
    Return talents with proper category strings and IDs.
    """
    talents = Talent.objects.all().order_by('-rating', '-reviews')
    data = []
    
    for t in talents:
        # Get category name and ID safely
        cat_obj = getattr(t, 'category', None)
        
        if isinstance(cat_obj, str):
            # It's already a string (e.g., CharField)
            cat_name = cat_obj
            cat_id = None
        elif cat_obj:
            # It's a related object (e.g., ForeignKey)
            cat_name = getattr(cat_obj, 'name', str(cat_obj))
            cat_id = getattr(cat_obj, 'id', None)
        else:
            # It's None or empty
            cat_name = ""
            cat_id = None

        data.append({
            'id': t.id,
            'name': t.name,
            'role': t.role,
            'category': cat_name,               # string for display
            'category_id': cat_id,              # integer for filtering
            'price': float(t.price) if t.price else 0,
            'duration': t.duration,
            'type': t.type,
            'location': t.location,
            'rating': t.rating,
            'reviews': t.reviews,
            'verified': t.verified,
            'skills': t.skills if isinstance(t.skills, list) else [],
            'image': get_image_url(t.image),
            'remote': t.remote,
            'experience': t.experience,
            'bio': t.bio,
            'tier': t.tier,
            'available_from': t.available_from,
            'portfolio': t.portfolio,
            'certifications': t.certifications,
            'languages': t.languages,
            'radius': t.radius,
            'top': t.top,
            'education': t.education,
            'createdAt': t.created_at.isoformat() if t.created_at else None,
        })
        
    return JsonResponse({'success': True, 'talents': data})


# ============================================================================
# API: REGISTER JOB SEEKER (from front page)
# ============================================================================

@csrf_exempt

@require_http_methods(["POST"])
def api_register_seeker(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    required = ['first_name', 'last_name', 'email', 'password']
    for field in required:
        if not data.get(field):
            return JsonResponse({'success': False, 'message': f'{field} is required'}, status=400)

    if User.objects.filter(email=data['email']).exists():
        return JsonResponse({'success': False, 'message': 'Account with this email already exists.'}, status=400)

    user = User.objects.create_user(
        username=data['email'],
        email=data['email'],
        password=data['password'],
        first_name=data['first_name'],
        last_name=data['last_name'],
    )

    # Optional fields – default if missing
    title = data.get('title', '')
    phone = data.get('phone', '')
    country = data.get('country', '')
    city = data.get('city', '')
    hourly_rate = data.get('rate', 0)
    experience = _parse_experience(data.get('experience', '0-1'))
    skills = data.get('skills', [])
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(',') if s.strip()]
    bio = data.get('bio', '')

    profile = JobSeekerProfile.objects.create(
        user=user,
        title=title,
        phone_number=phone,
        country=country,
        city=city,
        hourly_rate=hourly_rate,
        years_of_experience=experience,
        skills=skills,
        bio=bio,
        is_verified=False,
        email_verified=False,
        is_active=True,
    )

    group, _ = Group.objects.get_or_create(name='JobSeeker')
    user.groups.add(group)

    return JsonResponse({
        'success': True,
        'message': f'Account created for {user.get_full_name()}!',
        'user': {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'role': 'job_seeker',
            'profile_image': get_image_url(profile.profile_picture) if profile.profile_picture else None,
        }
    })

# ============================================================================
# API: REGISTER EMPLOYER (from front page)
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def api_register_employer(request):
    """Handle employer registration from the front page."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    required = ['company', 'first_name', 'last_name', 'email', 'password', 'phone']
    for field in required:
        if not data.get(field):
            return JsonResponse({'success': False, 'message': f'{field} is required'}, status=400)

    if User.objects.filter(email=data['email']).exists():
        return JsonResponse({
            'success': False,
            'message': 'An account with this email already exists.'
        }, status=400)

    user = User.objects.create_user(
        username=data['email'],
        email=data['email'],
        password=data['password'],
        first_name=data['first_name'],
        last_name=data['last_name'],
    )

    ClientProfile.objects.create(
        user=user,
        company_name=data.get('company', ''),
        location=data.get('address', ''),
        phone=data.get('phone', ''),
        website=data.get('website', ''),
        is_verified=False,
    )

    group, _ = Group.objects.get_or_create(name='Client')
    user.groups.add(group)

    return JsonResponse({
        'success': True,
        'message': f'Company account created for {data["company"]}!',
        'user_id': user.id,
    })


# ============================================================================
# API: SEEKER LOGIN (from front page)
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def api_seeker_login(request):
    """Handle job seeker login from the front page."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    email = data.get('email', '')
    password = data.get('password', '')

    if not email or not password:
        return JsonResponse({'success': False, 'message': 'Email and password are required'}, status=400)

    try:
        user_obj = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Invalid email or password'}, status=401)

    user = authenticate(request, username=user_obj.username, password=password)
    if user is not None:
        login(request, user)
        return JsonResponse({
            'success': True,
            'message': f'Welcome back, {user.get_full_name()}!',
            'redirect': '/dashboard/',
        })
    else:
        return JsonResponse({'success': False, 'message': 'Invalid email or password'}, status=401)


# ============================================================================
# API: EMPLOYER LOGIN (from front page)
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def api_employer_login(request):
    """Handle employer login from the front page."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    email = data.get('email', '')
    password = data.get('password', '')

    if not email or not password:
        return JsonResponse({'success': False, 'message': 'Email and password are required'}, status=400)

    try:
        user_obj = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Invalid email or password'}, status=401)

    user = authenticate(request, username=user_obj.username, password=password)
    if user is not None:
        login(request, user)
        return JsonResponse({
            'success': True,
            'message': f'Welcome back, {user.get_full_name()}!',
            'redirect': '/client/dashboard/',
        })
    else:
        return JsonResponse({'success': False, 'message': 'Invalid email or password'}, status=401)


# ============================================================================
# API: VERIFY JOB SEEKER
# ============================================================================

@csrf_exempt
@require_POST
def verify_job_seeker(request):
    """
    Toggle or set the verification status of a job seeker.
    Expects JSON: {"user_id": 123, "verified": true/false}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    verified = data.get('verified', True)

    if not user_id:
        return JsonResponse({'success': False, 'message': 'user_id required'}, status=400)

    user = get_object_or_404(User, id=user_id)
    profile = get_object_or_404(JobSeekerProfile, user=user)
    profile.is_verified = verified
    profile.save()

    return JsonResponse({
        'success': True,
        'message': f'User {user.get_full_name()} verification set to {verified}.',
        'verified': verified
    })


# ============================================================================
# API: GET SINGLE TALENT
# ============================================================================

@login_required
def get_talent(request, talent_id):
    """Get a single talent by ID."""
    talent = get_object_or_404(Talent, id=talent_id)
    
    return JsonResponse({
        'success': True,
        'talent': {
            'id': talent.id,
            'name': talent.name,
            'role': talent.role,
            'category': talent.category,
            'price': float(talent.price) if talent.price else 0,
            'rating': float(talent.rating) if talent.rating else 0,
            'reviews': talent.reviews,
            'location': talent.location,
            'duration': talent.duration,
            'bio': talent.bio,
            'skills': talent.skills if isinstance(talent.skills, list) else [],
            'languages': talent.languages if isinstance(talent.languages, list) else [],
            'image': get_image_url(talent.image),
            'verified': talent.verified,
            'top': talent.top,
            'remote': talent.remote,
            'experience': talent.experience,
            'tier': talent.tier,
        }
    })


# ============================================================================
# API: UPDATE TALENT (with ImageField support)
# ============================================================================

@login_required
@require_http_methods(["PUT", "POST", "PATCH"])
def update_talent(request, talent_id):
    """
    Update an existing Talent record via AJAX.
    Supports both JSON and FormData (for file uploads).
    """
    if not request.user.is_staff:
        logger.warning(f"User {request.user.username} attempted to update talent {talent_id} without permission")
        return JsonResponse({
            'success': False, 
            'message': 'Permission denied. Staff access required.'
        }, status=403)

    talent = get_object_or_404(Talent, id=talent_id)
    
    try:
        content_type = request.content_type or ''
        photo_file = None
        data = {}
        
        # Parse request data based on content type
        if 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
            data = request.POST.dict()
            photo_file = request.FILES.get('photo')
            logger.info(f" FormData received for talent {talent_id}")
            if photo_file:
                logger.info(f"📷 Photo: {photo_file.name}, size: {photo_file.size}, type: {photo_file.content_type}")
        else:
            try:
                raw_body = request.body.decode('utf-8')
                if not raw_body:
                    return JsonResponse({
                        'success': False,
                        'message': 'Request body is empty'
                    }, status=400)
                data = json.loads(raw_body)
                logger.info(f"📝 JSON received for talent {talent_id}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error for talent {talent_id}: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'message': f'Invalid JSON format: {str(e)}'
                }, status=400)

        # Define field categories
        allowed_fields = [
            'name', 'role', 'category', 'price', 'rating', 'reviews', 'location',
            'bio', 'duration', 'type', 'remote', 'verified', 'top', 'tier',
            'experience', 'education', 'skills', 'languages', 'certifications',
            'availability', 'radius', 'available_from', 'portfolio'
        ]
        
        list_fields = ['skills', 'languages', 'certifications', 'availability', 'portfolio']
        numeric_fields = ['price', 'rating', 'reviews', 'experience', 'tier', 'radius']
        boolean_fields = ['remote', 'verified', 'top']

        # Update regular fields
        updated_fields = []
        for field in allowed_fields:
            if field in data:
                value = data[field]
                
                # Parse JSON strings from FormData
                if isinstance(value, str) and value.startswith(('{', '[')):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
                
                # Handle list fields
                if field in list_fields:
                    if isinstance(value, str):
                        value = [item.strip() for item in value.split(',') if item.strip()]
                    elif not isinstance(value, list):
                        value = []
                
                # Handle numeric fields
                elif field in numeric_fields:
                    try:
                        value = float(value) if field == 'rating' else int(value)
                    except (ValueError, TypeError):
                        value = 0
                
                # Handle boolean fields
                elif field in boolean_fields:
                    if isinstance(value, str):
                        value = value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        value = bool(value)
                
                setattr(talent, field, value)
                updated_fields.append(field)

        # ✅ FIXED: Handle photo operations
        photo_removed = data.get('photo_removed', 'false')
        if isinstance(photo_removed, str):
            photo_removed = photo_removed.lower() in ('true', '1', 'yes')
        
        if photo_removed:
            # Remove existing photo
            if talent.image:
                try:
                    talent.image.delete(save=False)
                    logger.info(f"🗑️ Deleted old image file for talent {talent_id}")
                except Exception as e:
                    logger.warning(f"Could not delete old image: {e}")
            talent.image = None
            updated_fields.append('image')
            logger.info(f"🗑️ Removed photo reference from talent {talent_id}")
        
        elif photo_file:
            # ✅ FIXED: Upload new photo using proper Django file handling
            try:
                if photo_file.size > 5 * 1024 * 1024:
                    return JsonResponse({
                        'success': False,
                        'message': 'Photo too large. Maximum size is 5MB.'
                    }, status=400)
                
                allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
                if photo_file.content_type not in allowed_types:
                    return JsonResponse({
                        'success': False,
                        'message': f'Invalid file type. Allowed: {", ".join(allowed_types)}'
                    }, status=400)
                
                # Delete old image file
                if talent.image:
                    try:
                        talent.image.delete(save=False)
                        logger.info(f"🗑️ Deleted old image for talent {talent_id}")
                    except Exception as e:
                        logger.warning(f"Could not delete old image: {e}")
                
                # ✅ CRITICAL FIX: Use .save() method to properly save the file
                talent.image.save(photo_file.name, photo_file, save=False)
                updated_fields.append('image')
                logger.info(f"✅ Photo saved for talent {talent_id}: {talent.image.name}")
                
                # Verify file exists on disk
                if hasattr(talent.image, 'path') and os.path.exists(talent.image.path):
                    logger.info(f"✅ File exists on disk: {talent.image.path}")
                else:
                    logger.error(f" File NOT found on disk: {getattr(talent.image, 'path', 'No path')}")
                
            except Exception as e:
                logger.error(f"❌ Error uploading photo for talent {talent_id}: {str(e)}", exc_info=True)
                return JsonResponse({
                    'success': False,
                    'message': f'Error uploading photo: {str(e)}'
                }, status=500)
        
        elif 'photo_data' in data and data['photo_data']:
            # Handle base64 encoded photo
            try:
                photo_data = data['photo_data']
                if photo_data.startswith('data:image'):
                    format_str, imgstr = photo_data.split(';base64,')
                    ext = format_str.split('/')[-1]
                    data_file = ContentFile(base64.b64decode(imgstr), name=f'talent_{talent_id}.{ext}')
                    
                    if talent.image:
                        try:
                            talent.image.delete(save=False)
                        except:
                            pass
                    
                    talent.image.save(data_file.name, data_file, save=False)
                    updated_fields.append('image')
                    logger.info(f"✅ Base64 photo saved for talent {talent_id}")
            except Exception as e:
                logger.error(f"Error processing base64 photo for talent {talent_id}: {str(e)}")
        
        elif 'image' in data and data['image'] and not photo_file and not photo_removed:
            # Handle image URL: try to download and save
            image_value = data['image']
            if isinstance(image_value, str) and image_value.startswith(('http://', 'https://')):
                if talent.image:
                    try:
                        talent.image.delete(save=False)
                    except:
                        pass
                
                success = save_image_from_url(talent, image_value)
                if success:
                    updated_fields.append('image')
                    logger.info(f"✅ Image downloaded from URL for talent {talent_id}")
                else:
                    talent.image = None
                    logger.warning(f"Could not download image from URL for talent {talent_id}")

        # ✅ CRITICAL: Save the talent instance
        talent.save(update_fields=updated_fields if updated_fields else None)
        
        logger.info(
            f"Talent {talent.id} ({talent.name}) updated by {request.user.username}. "
            f"Updated fields: {', '.join(updated_fields) if updated_fields else 'none'}"
        )

        # Return success response with updated talent data
        return JsonResponse({
            'success': True,
            'message': f'Talent "{talent.name}" updated successfully!',
            'talent': {
                'id': talent.id,
                'name': talent.name,
                'role': talent.role,
                'category': talent.category,
                'price': float(talent.price) if talent.price else 0,
                'rating': float(talent.rating) if talent.rating else 0,
                'reviews': talent.reviews,
                'location': talent.location,
                'duration': talent.duration,
                'bio': talent.bio,
                'skills': talent.skills if isinstance(talent.skills, list) else [],
                'languages': talent.languages if isinstance(talent.languages, list) else [],
                'image': get_image_url(talent.image),
                'verified': talent.verified,
                'top': talent.top,
                'remote': talent.remote,
                'experience': talent.experience,
                'tier': talent.tier,
            }
        })

    except ValidationError as e:
        logger.error(f"Validation error updating talent {talent_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Validation error: {str(e)}'
        }, status=400)
    
    except Exception as e:
        logger.error(f"Unexpected error updating talent {talent_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'Server error: {str(e)}'
        }, status=500)
# ============================================================================
# API: UPLOAD TALENT PHOTO
# ============================================================================

@csrf_exempt
@require_POST
def api_upload_talent_photo(request):
    """
    Upload or update a talent's profile photo.
    Accepts multipart/form-data with 'talent_id' and 'photo' fields.
    """
    talent_id = request.POST.get('talent_id', '')
    photo_file = request.FILES.get('photo')

    if not talent_id:
        return JsonResponse({'success': False, 'message': 'Talent ID is required'}, status=400)

    if not photo_file:
        return JsonResponse({'success': False, 'message': 'Photo file is required'}, status=400)

    # Validate file type
    allowed_types = ['image/jpeg', 'image/png', 'image/webp']
    if photo_file.content_type not in allowed_types:
        return JsonResponse({
            'success': False,
            'message': 'Only JPG, PNG, and WebP images are allowed'
        }, status=400)

    # Validate file size (max 5MB for talent photos)
    if photo_file.size > 5 * 1024 * 1024:
        return JsonResponse({
            'success': False,
            'message': 'Image must be under 5MB'
        }, status=400)

    try:
        talent = Talent.objects.get(id=int(talent_id))
    except (Talent.DoesNotExist, ValueError):
        return JsonResponse({'success': False, 'message': 'Talent not found'}, status=404)

    try:
        # Delete old photo if exists
        if talent.image:
            try:
                talent.image.delete(save=False)
            except Exception:
                pass

        # Determine file extension
        ext_map = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}
        ext = ext_map.get(photo_file.content_type, 'jpg')
        filename = f"talent_{talent.id}_{int(timezone.now().timestamp())}.{ext}"

        # Save the new photo
        talent.image.save(filename, photo_file, save=True)

        photo_url = get_image_url(talent.image)

        logger.info(f"Photo uploaded for talent {talent.id}: {filename}")

        return JsonResponse({
            'success': True,
            'message': f'Photo updated for {talent.name}',
            'photo': photo_url,
        })

    except Exception as e:
        logger.error(f"Photo upload error for talent {talent_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to upload photo. Please try again.'
        }, status=500)


@csrf_exempt
@require_POST
def api_remove_talent_photo(request):
    """Remove a talent's profile photo."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)

    talent_id = data.get('talent_id')
    if not talent_id:
        return JsonResponse({'success': False, 'message': 'Talent ID is required'}, status=400)

    try:
        talent = Talent.objects.get(id=int(talent_id))
    except (Talent.DoesNotExist, ValueError):
        return JsonResponse({'success': False, 'message': 'Talent not found'}, status=404)

    if talent.image:
        try:
            talent.image.delete(save=False)
        except Exception:
            pass
        talent.image = None
        talent.save()

    return JsonResponse({
        'success': True,
        'message': f'Photo removed from {talent.name}'
    })


# ============================================================================
# API: BATCH FIX TALENT IMAGES (run once to fix URL-stored images)
# ============================================================================

@staff_member_required
def api_fix_talent_images(request):
    """
    One-time utility: download images stored as URLs in the talent.image field
    and save them as actual files. Run this if talents have URL strings instead
    of uploaded files.
    """
    fixed = 0
    errors = 0

    for talent in Talent.objects.all():
        # Check if image is stored as a URL string rather than a file
        if talent.image and hasattr(talent.image, 'url'):
            try:
                # If .path doesn't exist, it might be a URL string stored in ImageField
                talent.image.path
                continue  # File exists, skip
            except (NotImplementedError, ValueError, FileNotFoundError):
                pass

        # Check if image field contains a URL string
        image_value = talent.image
        if isinstance(image_value, str) and image_value.startswith('http'):
            if save_image_from_url(talent, image_value):
                fixed += 1
            else:
                errors += 1

    return JsonResponse({
        'success': True,
        'message': f'Fixed {fixed} images, {errors} errors',
        'fixed': fixed,
        'errors': errors,
    })
    
# ============================================================================
# TELEGRAM WEBHOOK
# ============================================================================

# jobs/views.py
# jobs/views.py
import json
import asyncio
import traceback
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

@csrf_exempt
def telegram_webhook(request):
    """Handle incoming Telegram webhook"""
    
    def make_response(data, status=200):
        response = JsonResponse(data, status=status)
        # Standard no-cache headers
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        # LiteSpeed-specific: tell LiteSpeed NOT to cache this
        response['X-Litespeed-Cache-Control'] = 'no-cache'
        return response
    
    if request.method != "POST":
        return make_response({"error": "Only POST allowed"}, 405)
    
    try:
        raw_body = request.body
        logger.info(f"[WEBHOOK] Body length: {len(raw_body)}")
        
        if not raw_body:
            logger.error("[WEBHOOK] Empty body")
            return make_response({"ok": True})
        
        data = json.loads(raw_body)
        logger.info(f"[WEBHOOK] update_id: {data.get('update_id')}")
        
        from .bot import application
        from telegram import Update
        
        update = Update.de_json(data, application.bot)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(application.process_update(update))
        finally:
            loop.close()
            
        return make_response({"ok": True})
        
    except Exception as e:
        logger.error(f"[WEBHOOK ERROR] {str(e)}")
        traceback.print_exc()
        return make_response({"ok": True})
        
def mini_app(request):
    """
    Serve the Telegram Mini App HTML page.
    This is loaded when users open the app from the bot's menu button.
    """
    return render(request, 'miniapp/index.html')
    
@csrf_exempt

def api_login(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return JsonResponse({'success': False, 'error': 'Email and password required'}, status=400)

    user = authenticate(request, username=email, password=password)
    if user is None:
        return JsonResponse({'success': False, 'error': 'Invalid credentials'}, status=401)

    login(request, user)

    role = 'job_seeker'
    profile_image = None
    if hasattr(user, 'client_profile'):
        role = 'employer'
    elif hasattr(user, 'job_seeker_profile'):
        profile = user.job_seeker_profile
        profile_image = get_image_url(profile.profile_picture) if profile.profile_picture else None

    return JsonResponse({
        'success': True,
        'message': f'Welcome back, {user.get_full_name()}!',
        'user': {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': role,
            'profile_image': profile_image,
        }
    })
    
def api_categories(request):
    """
    Return categories for filter chips.
    If you have a Category model (e.g., JobCategory), use it.
    Otherwise, extract distinct category names from Talent.
    """
    # Option 1: If you have a dedicated Category model (recommended)
    if hasattr(settings, 'CATEGORY_MODEL') or 'JobCategory' in globals():
        from .models import JobCategory
        cats = JobCategory.objects.all()
        data = [{'id': c.id, 'name': c.name} for c in cats]
    else:
        # Fallback: get distinct category strings from Talent
        # If category is a ForeignKey, we need to get the name via the related object.
        # We'll use a set to avoid duplicates.
        categories = set()
        for t in Talent.objects.select_related('category').all():
            if t.category:
                if hasattr(t.category, 'name'):
                    categories.add((t.category.id, t.category.name))
                else:
                    categories.add((t.category, t.category))  # fallback
        data = [{'id': cat_id, 'name': cat_name} for cat_id, cat_name in categories]
        # If no categories, return empty list
    return JsonResponse({'success': True, 'categories': data})
    
from django.contrib.auth.decorators import login_required


@csrf_exempt
def api_current_user(request):
    """
    Return the currently signed-in user as JSON.

    Deliberately NOT wrapped in @login_required: that decorator redirects
    anonymous callers to the HTML login page, which breaks JSON clients
    such as the Telegram mini app. Return 401 with JSON instead.
    """
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({'authenticated': False, 'user': None}, status=401)

    role = 'job_seeker'
    profile_image = None
    if hasattr(user, 'client_profile'):
        role = 'employer'
    elif hasattr(user, 'job_seeker_profile'):
        profile = user.job_seeker_profile
        profile_image = get_image_url(profile.profile_picture) if profile.profile_picture else None

    return JsonResponse({
        'authenticated': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': role,
            'profile_image': profile_image,
        }
    })
    
@csrf_exempt
def api_logout(request):
    from django.contrib.auth import logout as django_logout
    django_logout(request)
    return JsonResponse({'success': True, 'message': 'Logged out'})
    
@csrf_exempt
@require_POST
def api_toggle_verify(request, seeker_id):
    """
    Toggle verification status for a job seeker.
    Expects: /api/job-seekers/<seeker_id>/toggle-verify/
    """
    try:
        profile = JobSeekerProfile.objects.select_related('user').get(id=seeker_id)
    except JobSeekerProfile.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Job seeker not found'}, status=404)
    
    profile.is_verified = not profile.is_verified
    profile.save()
    
    status = 'verified' if profile.is_verified else 'unverified'
    return JsonResponse({
        'success': True,
        'message': f'User {profile.user.get_full_name()} is now {status}.',
        'verified': profile.is_verified
    })
    
# jobs/views.py
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import JobSeekerProfile

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def verify_job_seeker(request):
    """
    Toggle or set the verification status of a job seeker.
    Expects JSON: {"user_id": 123, "verified": true/false}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    verified = data.get('verified')

    if user_id is None or verified is None:
        return JsonResponse({'success': False, 'message': 'user_id and verified are required'}, status=400)

    try:
        profile = JobSeekerProfile.objects.select_related('user').get(user_id=user_id)
    except JobSeekerProfile.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Job seeker not found'}, status=404)

    # ✅ Actually update the database
    profile.is_verified = bool(verified)
    profile.save(update_fields=['is_verified'])

    logger.info(f"Verification updated for user {profile.user.email}: is_verified={profile.is_verified}")

    return JsonResponse({
        'success': True,
        'message': f'User {profile.user.get_full_name()} is now {"verified" if profile.is_verified else "unverified"}.',
        'verified': profile.is_verified
    })
    
# example in Django REST Framework / Views
import os
from django.http import JsonResponse

def protected_api_view(request):
    client_api_key = request.headers.get('X-Ethiogen-Api-Key')
    server_api_key = os.getenv('ETHIOGEN_API_KEY')
    
    if not client_api_key or client_api_key != server_api_key:
        return JsonResponse({'error': 'Unauthorized: Invalid API Key'}, status=401)
        
    # Process request if valid
    return JsonResponse({'message': 'Authenticated successfully'})
    
# jobs/views.py - add this function

@csrf_exempt
def api_jobs(request):
    """
    JSON API endpoint for jobs list.
    Returns all approved jobs with their details.
    """
    # Filter to show only approved jobs (adjust as needed)
    jobs = Job.objects.filter(is_approved=True).order_by('-posted_date')
    
    data = []
    for job in jobs:
        data.append({
            'id': job.id,
            'title': job.title,
            'company': job.company_name or 'Unknown Company',
            'location': job.location or 'Remote',
            'job_type': job.employment_type or 'Full-time',
            'salary': str(job.salary) if job.salary else 'Negotiable',
            'description': job.description,
            'category': job.category or '',
            'posted_date': job.posted_date.isoformat() if job.posted_date else None,
            'is_approved': job.is_approved,
            'experience_required': job.experience_required or 0,
        })
    
    return JsonResponse({
        'success': True,
        'count': len(data),
        'jobs': data
    })


@csrf_exempt
def api_job_detail(request, job_id):
    """
    JSON API endpoint for single job detail.
    """
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Job not found'}, status=404)
    
    return JsonResponse({
        'success': True,
        'job': {
            'id': job.id,
            'title': job.title,
            'company': job.company_name or 'Unknown Company',
            'location': job.location or 'Remote',
            'job_type': job.employment_type or 'Full-time',
            'salary': str(job.salary) if job.salary else 'Negotiable',
            'description': job.description,
            'category': job.category or '',
            'posted_date': job.posted_date.isoformat() if job.posted_date else None,
            'is_approved': job.is_approved,
            'experience_required': job.experience_required or 0,
            'employer_email': job.client.user.email if hasattr(job, 'client') else None,
        }
    })
    
