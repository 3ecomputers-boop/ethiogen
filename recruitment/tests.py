from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from jobs.models import ClientProfile, Job, JobSeekerProfile

from .models import Application, ApplicationEvent

User = get_user_model()


class RecruitmentATSTests(TestCase):
    def setUp(self):
        self.employer_user = User.objects.create_user(
            username='employer',
            password='test-pass-123',
            first_name='Meron',
            last_name='Tesfaye',
        )
        self.client_profile = ClientProfile.objects.create(
            user=self.employer_user,
            company_name='Acme Systems',
            location='Addis Ababa',
        )
        self.other_employer = User.objects.create_user(
            username='other-employer',
            password='test-pass-123',
        )
        self.other_client = ClientProfile.objects.create(
            user=self.other_employer,
            company_name='Other Co',
        )
        self.staff_user = User.objects.create_user(
            username='staff',
            password='test-pass-123',
            is_staff=True,
        )
        self.seeker_user = User.objects.create_user(
            username='seeker',
            password='test-pass-123',
            first_name='Sara',
            last_name='Kebede',
        )
        self.seeker_profile = JobSeekerProfile.objects.create(
            user=self.seeker_user,
            title='Django Developer',
            city='Addis Ababa',
            skills=['Python', 'Django'],
            years_of_experience=3,
            is_verified=True,
        )

        self.job = Job.objects.create(
            title='Django Developer',
            company_name='Acme Systems',
            description='Build APIs.',
            location='Addis Ababa',
            employment_type='Full-time',
            experience_required=2,
            client=self.client_profile,
            is_approved=True,
        )
        self.application = Application.objects.create(
            applicant=self.seeker_user,
            job=self.job,
            cover_letter='I would like to join the team.',
        )

    def test_application_creation_creates_timeline_event(self):
        event = self.application.events.get()

        self.assertEqual(event.event_type, ApplicationEvent.EVENT_CREATED)
        self.assertEqual(event.actor, self.seeker_user)
        self.assertEqual(event.to_status, Application.STATUS_SUBMITTED)

    def test_status_change_creates_timeline_event(self):
        self.application._event_actor = self.employer_user
        self.application.status = Application.STATUS_SHORTLISTED
        self.application.save(update_fields=['status', 'updated_at'])

        event = self.application.events.first()

        self.assertEqual(event.event_type, ApplicationEvent.EVENT_STATUS)
        self.assertEqual(event.from_status, Application.STATUS_SUBMITTED)
        self.assertEqual(event.to_status, Application.STATUS_SHORTLISTED)
        self.assertEqual(event.actor, self.employer_user)

    def test_add_note_creates_timeline_event(self):
        self.client.force_login(self.employer_user)

        response = self.client.post(
            reverse('recruitment:add_application_note', args=[self.application.pk]),
            {'note': 'Strong portfolio; invite for interview.'},
        )

        self.assertRedirects(
            response,
            reverse('recruitment:ats_application_detail', args=[self.application.pk]),
        )
        self.assertTrue(
            self.application.events.filter(
                event_type=ApplicationEvent.EVENT_NOTE,
                note='Strong portfolio; invite for interview.',
            ).exists()
        )

    def test_ats_dashboard_requires_employer_profile(self):
        self.client.force_login(self.seeker_user)

        response = self.client.get(reverse('recruitment:ats_dashboard'))

        self.assertEqual(response.status_code, 403)

    def test_ats_dashboard_lists_only_own_jobs(self):
        other_job = Job.objects.create(
            title='Other role',
            company_name='Other Co',
            description='Other work.',
            location='Addis Ababa',
            client=self.other_client,
            is_approved=True,
        )
        self.client.force_login(self.employer_user)

        response = self.client.get(reverse('recruitment:ats_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.job.title)
        self.assertNotContains(response, other_job.title)

    def test_pipeline_permissions(self):
        self.client.force_login(self.employer_user)
        response = self.client.get(
            reverse('recruitment:ats_job_pipeline', args=[self.job.pk])
        )
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.other_employer)
        response = self.client.get(
            reverse('recruitment:ats_job_pipeline', args=[self.job.pk])
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse('recruitment:ats_job_pipeline', args=[self.job.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_status_update_changes_stage_for_owner(self):
        self.client.force_login(self.employer_user)

        response = self.client.post(
            reverse('recruitment:update_application_status', args=[self.application.pk]),
            {'status': Application.STATUS_INTERVIEW},
        )

        self.assertRedirects(
            response,
            reverse('recruitment:ats_application_detail', args=[self.application.pk]),
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.STATUS_INTERVIEW)

    def test_status_update_rejects_non_owner(self):
        self.client.force_login(self.other_employer)

        response = self.client.post(
            reverse('recruitment:update_application_status', args=[self.application.pk]),
            {'status': Application.STATUS_HIRED},
        )

        self.assertEqual(response.status_code, 403)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.STATUS_SUBMITTED)

    def test_invalid_status_is_ignored(self):
        self.client.force_login(self.employer_user)

        response = self.client.post(
            reverse('recruitment:update_application_status', args=[self.application.pk]),
            {'status': 'not-a-real-stage'},
        )

        self.assertRedirects(
            response,
            reverse('recruitment:ats_application_detail', args=[self.application.pk]),
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.STATUS_SUBMITTED)

    def test_my_applications_shows_status(self):
        self.client.force_login(self.seeker_user)

        response = self.client.get(reverse('recruitment:my_applications'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.job.title)
        self.assertContains(response, 'Submitted')

    def test_application_detail_shows_cover_letter(self):
        self.client.force_login(self.employer_user)

        response = self.client.get(
            reverse('recruitment:ats_application_detail', args=[self.application.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'I would like to join the team.')
        self.assertContains(response, self.seeker_user.get_full_name())

    def test_apply_for_job_creates_application_and_blocks_duplicates(self):
        job = Job.objects.create(
            title='Backend Engineer',
            company_name='Acme Systems',
            description='Build services.',
            location='Addis Ababa',
            client=self.client_profile,
            is_approved=True,
        )
        self.client.force_login(self.seeker_user)

        response = self.client.post(
            reverse('recruitment:apply_for_job', args=[job.pk]),
            {'cover_letter': 'Please consider my application.'},
        )

        self.assertRedirects(response, reverse('recruitment:my_applications'))
        self.assertTrue(
            Application.objects.filter(job=job, applicant=self.seeker_user).exists()
        )

        response = self.client.get(
            reverse('recruitment:apply_for_job', args=[job.pk])
        )
        self.assertRedirects(response, reverse('recruitment:my_applications'))

    def test_job_list_hides_unapproved_jobs(self):
        hidden = Job.objects.create(
            title='Hidden role',
            company_name='Acme Systems',
            description='Not approved.',
            location='Addis Ababa',
            client=self.client_profile,
            is_approved=False,
        )
        self.client.force_login(self.seeker_user)

        response = self.client.get(reverse('recruitment:job_postings'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, hidden.title)

    def test_create_job_posting_sets_pending_and_owner(self):
        self.client.force_login(self.employer_user)

        response = self.client.post(
            reverse('recruitment:create_job_posting'),
            {
                'title': 'New Role',
                'company_name': 'Acme Systems',
                'description': 'New work.',
                'location': 'Addis Ababa',
                'employment_type': 'Full-time',
                'experience_required': '1',
            },
        )

        self.assertRedirects(response, reverse('recruitment:ats_dashboard'))
        job = Job.objects.get(title='New Role')
        self.assertEqual(job.client, self.client_profile)
        self.assertFalse(job.is_approved)

    def test_create_job_posting_requires_employer_profile(self):
        self.client.force_login(self.seeker_user)

        response = self.client.get(reverse('recruitment:create_job_posting'))

        self.assertRedirects(response, reverse('jobs:client_profile'))

    def test_bulk_update_status_moves_selected(self):
        job2 = Job.objects.create(
            title='Second Role',
            company_name='Acme Systems',
            description='More work.',
            location='Addis Ababa',
            client=self.client_profile,
            is_approved=True,
        )
        app2 = Application.objects.create(
            applicant=self.seeker_user,
            job=job2,
            cover_letter='Another application.',
        )
        self.client.force_login(self.employer_user)

        response = self.client.post(
            reverse('recruitment:bulk_update_application_status'),
            {
                'application_ids': [self.application.pk, app2.pk],
                'status': Application.STATUS_SHORTLISTED,
            },
        )

        self.assertRedirects(response, reverse('recruitment:ats_dashboard'))
        self.application.refresh_from_db()
        app2.refresh_from_db()
        self.assertEqual(self.application.status, Application.STATUS_SHORTLISTED)
        self.assertEqual(app2.status, Application.STATUS_SHORTLISTED)
        self.assertTrue(
            self.application.events.filter(
                event_type=ApplicationEvent.EVENT_STATUS,
                to_status=Application.STATUS_SHORTLISTED,
            ).exists()
        )

    def test_bulk_update_skips_applications_not_owned(self):
        other_job = Job.objects.create(
            title='Other Role',
            company_name='Other Co',
            description='Other work.',
            location='Addis Ababa',
            client=self.other_client,
            is_approved=True,
        )
        other_app = Application.objects.create(
            applicant=self.seeker_user,
            job=other_job,
            cover_letter='Other app.',
        )
        self.client.force_login(self.employer_user)

        response = self.client.post(
            reverse('recruitment:bulk_update_application_status'),
            {
                'application_ids': [self.application.pk, other_app.pk],
                'status': Application.STATUS_HIRED,
            },
        )

        self.assertRedirects(response, reverse('recruitment:ats_dashboard'))
        self.application.refresh_from_db()
        other_app.refresh_from_db()
        self.assertEqual(self.application.status, Application.STATUS_HIRED)
        self.assertEqual(other_app.status, Application.STATUS_SUBMITTED)

    def test_bulk_update_rejects_invalid_status(self):
        self.client.force_login(self.employer_user)

        response = self.client.post(
            reverse('recruitment:bulk_update_application_status'),
            {
                'application_ids': [self.application.pk],
                'status': 'not-a-stage',
            },
        )

        self.assertRedirects(response, reverse('recruitment:ats_dashboard'))
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.STATUS_SUBMITTED)

    def test_export_applications_csv(self):
        self.client.force_login(self.employer_user)

        response = self.client.get(
            reverse('recruitment:export_applications_csv', args=[self.job.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment; filename=', response['Content-Disposition'])
        content = response.content.decode('utf-8')
        self.assertIn('Application ID', content)
        self.assertIn(self.seeker_user.get_full_name(), content)
        self.assertIn('Submitted', content)

    def test_export_csv_requires_job_access(self):
        other_job = Job.objects.create(
            title='Other Role',
            company_name='Other Co',
            description='Other work.',
            location='Addis Ababa',
            client=self.other_client,
            is_approved=True,
        )
        self.client.force_login(self.employer_user)

        response = self.client.get(
            reverse('recruitment:export_applications_csv', args=[other_job.pk])
        )

        self.assertEqual(response.status_code, 403)

