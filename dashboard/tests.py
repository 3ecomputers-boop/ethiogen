from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from jobs.models import ClientProfile, JobSeekerProfile, VerificationEvent

User = get_user_model()


class VerificationQueueTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='staff', password='pass-123', is_staff=True, is_superuser=True
        )
        self.nonstaff = User.objects.create_user(
            username='regular', password='pass-123'
        )

        self.seeker_user = User.objects.create_user(
            username='seeker', password='pass-123'
        )
        self.seeker = JobSeekerProfile.objects.create(
            user=self.seeker_user,
            title='Django Developer',
            city='Addis Ababa',
            is_verified=False,
            is_active=True,
        )

        self.client_user = User.objects.create_user(
            username='client_owner', password='pass-123'
        )
        self.client_profile = ClientProfile.objects.create(
            user=self.client_user,
            company_name='Acme Systems',
            location='Addis Ababa',
            is_verified=False,
        )

    def _force(self, user):
        self.client.force_login(user)

    def test_queue_requires_staff(self):
        self._force(self.nonstaff)
        response = self.client.get(reverse('dashboard:verifications'))

        # Non-staff users are redirected to login, matching existing dashboard views.
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_queue_shows_pending_seekers(self):
        self._force(self.staff)
        response = self.client.get(reverse('dashboard:verifications'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Django Developer')
        self.assertContains(response, 'seeker')

    def test_queue_tabs_show_clients(self):
        self._force(self.staff)
        response = self.client.get(reverse('dashboard:verifications') + '?type=client')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Acme Systems')

    def test_approve_seeker_creates_event(self):
        self._force(self.staff)
        response = self.client.post(
            reverse('dashboard:verification_action', args=['seeker', self.seeker.pk]),
            {'type': 'seeker', 'decision': 'approve'},
        )
        self.assertEqual(response.status_code, 302)
        self.seeker.refresh_from_db()
        self.assertTrue(self.seeker.is_verified)
        self.assertTrue(VerificationEvent.objects.filter(
            job_seeker=self.seeker,
            action=VerificationEvent.ACTION_APPROVED,
            actor=self.staff,
        ).exists())

    def test_reject_client_creates_event(self):
        self.client_profile.is_verified = True
        self.client_profile.save(update_fields=['is_verified'])
        self._force(self.staff)
        response = self.client.post(
            reverse('dashboard:verification_action', args=['client', self.client_profile.pk]),
            {'type': 'client', 'decision': 'reject', 'note': 'Missing documents.'},
        )
        self.assertEqual(response.status_code, 302)
        self.client_profile.refresh_from_db()
        self.assertFalse(self.client_profile.is_verified)
        event = VerificationEvent.objects.get(client=self.client_profile)
        self.assertEqual(event.action, VerificationEvent.ACTION_REJECTED)
        self.assertEqual(event.note, 'Missing documents.')
        self.assertEqual(event.actor, self.staff)

    def test_non_staff_cannot_decide(self):
        self._force(self.nonstaff)
        response = self.client.post(
            reverse('dashboard:verification_action', args=['seeker', self.seeker.pk]),
            {'type': 'seeker', 'decision': 'approve'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)
        self.seeker.refresh_from_db()
        self.assertFalse(self.seeker.is_verified)

    def test_already_verified_is_noop(self):
        self.seeker.is_verified = True
        self.seeker.save(update_fields=['is_verified'])
        self._force(self.staff)
        response = self.client.post(
            reverse('dashboard:verification_action', args=['seeker', self.seeker.pk]),
            {'type': 'seeker', 'decision': 'approve'},
        )
        self.assertRedirects(response, reverse('dashboard:verifications') + '?type=seeker')
        self.assertEqual(VerificationEvent.objects.filter(job_seeker=self.seeker).count(), 0)

    def test_recent_events_shown(self):
        VerificationEvent.objects.create(
            job_seeker=self.seeker,
            actor=self.staff,
            action=VerificationEvent.ACTION_APPROVED,
            note='Approved from queue.',
        )
        self._force(self.staff)
        response = self.client.get(reverse('dashboard:verifications'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Django Developer')
        self.assertContains(response, 'Approved')
        self.assertContains(response, 'staff')
