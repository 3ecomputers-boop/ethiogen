# jobs/signals.py
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import JobSeekerProfile, Talent

logger = logging.getLogger(__name__)

@receiver(post_save, sender=JobSeekerProfile)
def sync_talent_on_verification(sender, instance, created, **kwargs):
    """
    Sync JobSeekerProfile to Talent on verification.
    Only updates if profile has a picture OR talent doesn't have one.
    """
    # Only proceed if the profile is verified and active
    if not (instance.is_verified and instance.is_active):
        return

    # Build default values
    image_url = (
        instance.profile_picture.url
        if instance.profile_picture and hasattr(instance.profile_picture, 'url') and instance.profile_picture.name
        else '/static/images/default-avatar.png'
    )
    category_name = instance.category.name if instance.category else 'General'
    price = int(instance.hourly_rate * 160) if instance.hourly_rate else 0
    sub_ratings = {
        'quality': float(instance.average_rating) if instance.average_rating else 4.5,
        'punctuality': 4.5,
        'communication': 4.5,
    }

    # Get or create Talent with all required fields set on creation
    talent, created = Talent.objects.get_or_create(
        profile=instance,
        defaults={
            'name': instance.get_full_name(),
            'role': instance.title or 'Professional',
            'location': instance.location or 'Addis Ababa',
            'bio': instance.bio or 'Experienced professional.',
            'image': image_url if instance.profile_picture and instance.profile_picture.name else None,
            'category': category_name,
            'experience': instance.years_of_experience or 0,
            'education': "Bachelor's degree",
            'skills': instance.skills if isinstance(instance.skills, list) else [],
            'certifications': [],
            'languages': ['English'],
            'price': price,
            'duration': 'Monthly',
            'type': 'Full-time',
            'available_from': 7,
            'availability': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
            'radius': 100,
            'remote': False,
            'rating': float(instance.average_rating) if instance.average_rating else 4.0,
            'reviews': 0,
            'sub_ratings': sub_ratings,
            'portfolio': [],
            'verified': instance.is_verified,
            'top': False,
            'tier': 1,
        }
    )

    # If the Talent already existed, update its fields with the latest data
    if not created:
        talent.name = instance.get_full_name()
        talent.role = instance.title or 'Professional'
        talent.location = instance.location or 'Addis Ababa'
        talent.bio = instance.bio or 'Experienced professional.'
        
        # ✅ ONLY update image if profile has a picture
        if instance.profile_picture and instance.profile_picture.name:
            talent.image = instance.profile_picture
        
        talent.category = category_name
        talent.experience = instance.years_of_experience or 0
        talent.skills = instance.skills if isinstance(instance.skills, list) else []
        talent.price = price
        talent.rating = float(instance.average_rating) if instance.average_rating else 4.0
        talent.verified = instance.is_verified
        talent.save()
        logger.info(f"Updated Talent for {instance.user.username}")
    else:
        logger.info(f"Created Talent for {instance.user.username}")