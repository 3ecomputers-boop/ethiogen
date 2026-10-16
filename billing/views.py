"""Public endpoints for the billing flow."""
import json
import logging

from django.contrib.auth import login
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import handle_chapa_webhook

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def telegram_login(request: HttpRequest) -> JsonResponse:
    """
    One-tap sign-in from inside the Telegram mini app.

    The client posts the signed initData blob; we verify the HMAC before
    trusting any user id, then log the matching Django user in.
    """
    from .telegram_auth import upsert_user_from_telegram, verify_init_data

    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse(
            {'success': False, 'error': 'Invalid JSON'}, status=400
        )

    result = verify_init_data(payload.get('initData') or payload.get('init_data') or '')
    if not result['ok']:
        logger.info('Telegram login rejected: %s', result['error'])
        return JsonResponse(
            {'success': False, 'error': result['error']}, status=403
        )

    try:
        user, created = upsert_user_from_telegram(result['user'])
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')

    profile = getattr(user, 'job_seeker_profile', None)
    employer = getattr(user, 'client_profile', None)
    if employer is not None:
        role = 'employer'
    elif profile is not None:
        role = 'job_seeker'
    else:
        role = 'new'

    return JsonResponse({
        'success': True,
        'created': created,
        'user': {
            'id': user.pk,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'role': role,
        },
    })


@csrf_exempt
@require_POST
def chapa_webhook(request: HttpRequest) -> JsonResponse:
    """
    Receive Chapa payment notifications.

    Always returns 200 so Chapa does not retry on a handler error; the real
    outcome is logged.
    """
    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        logger.warning('Chapa webhook sent invalid JSON')
        return JsonResponse({'received': False, 'error': 'invalid json'}, status=200)

    logger.info('Chapa webhook: status=%s ref=%s',
                payload.get('status'),
                (payload.get('data') or {}).get('reference'))

    try:
        subscription = handle_chapa_webhook(payload)
    except Exception as exc:
        logger.exception('Chapa webhook processing failed')
        return JsonResponse({'received': True, 'error': str(exc)}, status=200)

    return JsonResponse({
        'received': True,
        'subscription_id': subscription.pk if subscription else None,
        'status': subscription.status if subscription else None,
    })
