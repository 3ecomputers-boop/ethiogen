from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from jobs.models import Category, ClientProfile, Job, JobSeekerProfile, Profession

from .services import calculate_match, rank_candidates_for_job, rank_jobs_for_profile

User = get_user_model()


class MatchingServiceTests(TestCase):
    def setUp(self):
        self.seeker_user = User.objects.create_user(
            username='seeker',
            password='test-pass-123',
            first_name='Sara',
            last_name='Kebede',
        )
        self.category = Category.objects.create(name='Software')
        self.django_skill = Profession.objects.create(name='Django')
        self.python_skill = Profession.objects.create(name='Python')

        self.profile = JobSeekerProfile.objects.create(
            user=self.seeker_user,
            title='Django Developer',
            profession=self.django_skill,
            category=self.category,
            bio='Backend developer focused on reliable web applications.',
            city='Addis Ababa',
            location='Addis Ababa, Ethiopia',
            country='ET',
            years_of_experience=5,
            skills=['Python', 'Django', 'PostgreSQL', 'REST APIs'],
            hourly_rate=500,
            is_verified=True,
        )

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

        self.job = Job.objects.create(
            title='Senior Django Developer',
            company_name='Acme Systems',
            description='Build and maintain Django services.',
            category='Software',
            location='Addis Ababa, Ethiopia',
            experience_required=3,
            client=self.client_profile,
            is_approved=True,
        )
        self.job.required_skills.add(self.python_skill, self.django_skill)

    def test_match_score_is_bounded_and_explained(self):
        result = calculate_match(self.profile, self.job)

        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 100)
        self.assertEqual(len(result.components), 6)
        self.assertTrue(any('required skills' in reason for reason in result.reasons))
        self.assertTrue(result.reasons)

    def test_breakdown_points_add_up_to_score(self):
        result = calculate_match(self.profile, self.job)
        self.assertAlmostEqual(
            sum(component.points for component in result.components),
            result.score,
            delta=1.0,
        )

    def test_missing_skills_are_reported_as_gaps(self):
        welding = Profession.objects.create(name='Welding')
        self.job.required_skills.add(welding)

        result = calculate_match(self.profile, self.job)

        self.assertTrue(any('Missing required skills' in gap for gap in result.gaps))

    def test_location_mismatch_is_explained(self):
        self.job.location = 'Mekelle, Ethiopia'
        self.job.save(update_fields=['location'])

        result = calculate_match(self.profile, self.job)

        self.assertTrue(any('Mekelle' in gap for gap in result.gaps))

    def test_experience_shortfall_is_explained(self):
        self.profile.years_of_experience = 1
        self.profile.save(update_fields=['years_of_experience'])

        result = calculate_match(self.profile, self.job)

        self.assertTrue(any('1 years of experience vs 3 required' in gap for gap in result.gaps))

    def test_verified_profile_scores_higher_than_unverified(self):
        unverified_user = User.objects.create_user(
            username='unverified',
            password='test-pass-123',
        )
        unverified = JobSeekerProfile.objects.create(
            user=unverified_user,
            title=self.profile.title,
            profession=self.django_skill,
            category=self.category,
            bio=self.profile.bio,
            city=self.profile.city,
            location=self.profile.location,
            country=self.profile.country,
            years_of_experience=self.profile.years_of_experience,
            skills=list(self.profile.skills),
            hourly_rate=self.profile.hourly_rate,
            is_verified=False,
        )

        verified_result = calculate_match(self.profile, self.job)
        unverified_result = calculate_match(unverified, self.job)

        self.assertGreater(verified_result.score, unverified_result.score)

    def test_job_ranking_excludes_unapproved_jobs(self):
        Job.objects.create(
            title='Unapproved role',
            company_name='Acme Systems',
            description='Not visible yet.',
            location='Addis Ababa',
            is_approved=False,
        )

        results = rank_jobs_for_profile(self.profile, limit=None)

        self.assertTrue(results)
        self.assertTrue(all(result.job.is_approved for result in results))
        self.assertNotIn('Unapproved role', [result.job.title for result in results])

    def test_candidate_ranking_excludes_inactive_profiles(self):
        inactive_user = User.objects.create_user(
            username='inactive',
            password='test-pass-123',
        )
        inactive = JobSeekerProfile.objects.create(
            user=inactive_user,
            title='Django Developer',
            city='Addis Ababa',
            skills=['Python', 'Django'],
            is_active=False,
        )

        results = rank_candidates_for_job(self.job, limit=None)

        self.assertNotIn(inactive, [result.profile for result in results])


class MatchingViewTests(TestCase):
    def setUp(self):
        self.seeker_user = User.objects.create_user(
            username='seeker',
            password='test-pass-123',
            first_name='Sara',
            last_name='Kebede',
        )
        self.profile = JobSeekerProfile.objects.create(
            user=self.seeker_user,
            title='Django Developer',
            city='Addis Ababa',
            location='Addis Ababa, Ethiopia',
            country='ET',
            years_of_experience=4,
            skills=['Python', 'Django'],
            is_verified=True,
        )
        self.employer_user = User.objects.create_user(
            username='employer',
            password='test-pass-123',
        )
        self.client_profile = ClientProfile.objects.create(
            user=self.employer_user,
            company_name='Acme Systems',
        )
        self.other_employer = User.objects.create_user(
            username='other-employer',
            password='test-pass-123',
        )
        ClientProfile.objects.create(user=self.other_employer, company_name='Other Co')
        self.staff_user = User.objects.create_user(
            username='staff',
            password='test-pass-123',
            is_staff=True,
        )

        self.job = Job.objects.create(
            title='Django Developer',
            company_name='Acme Systems',
            description='Build APIs.',
            location='Addis Ababa',
            experience_required=2,
            client=self.client_profile,
            is_approved=True,
        )
        self.job.required_skills.add(Profession.objects.create(name='Django'))

    def test_job_seeker_matches_page_requires_profile(self):
        user_without_profile = User.objects.create_user(
            username='no-profile',
            password='test-pass-123',
        )
        self.client.force_login(user_without_profile)

        response = self.client.get(reverse('ai_engine:job_matches'))

        self.assertRedirects(
            response,
            reverse('jobs:create_job_seeker_profile'),
            fetch_redirect_response=False,
        )

    def test_job_seeker_matches_page_shows_approved_job(self):
        self.client.force_login(self.seeker_user)

        response = self.client.get(reverse('ai_engine:job_matches'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.job.title)
        self.assertContains(response, 'Why this matches')

    def test_job_seeker_api_returns_matches(self):
        self.client.force_login(self.seeker_user)

        response = self.client.get(reverse('ai_engine:api_job_matches'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['matches'][0]['job_id'], self.job.pk)
        self.assertIn('breakdown', data['matches'][0])

    def test_job_seeker_api_requires_profile(self):
        user_without_profile = User.objects.create_user(
            username='no-profile-api',
            password='test-pass-123',
        )
        self.client.force_login(user_without_profile)

        response = self.client.get(reverse('ai_engine:api_job_matches'))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])

    def test_employer_can_view_candidates_for_own_job(self):
        self.client.force_login(self.employer_user)

        response = self.client.get(
            reverse('ai_engine:job_candidates', args=[self.job.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.seeker_user.get_full_name())
        self.assertContains(response, 'Why this candidate')

    def test_non_owner_cannot_view_candidates(self):
        self.client.force_login(self.other_employer)

        response = self.client.get(
            reverse('ai_engine:job_candidates', args=[self.job.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_candidates(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse('ai_engine:job_candidates', args=[self.job.pk])
        )

        self.assertEqual(response.status_code, 200)

    def test_employer_candidate_api_is_protected(self):
        self.client.force_login(self.other_employer)

        response = self.client.get(
            reverse('ai_engine:api_job_candidates', args=[self.job.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_employer_candidate_api_returns_ranked_candidates(self):
        self.client.force_login(self.employer_user)

        response = self.client.get(
            reverse('ai_engine:api_job_candidates', args=[self.job.pk])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['job']['id'], self.job.pk)
        self.assertEqual(data['matches'][0]['profile_id'], self.profile.pk)

    def test_employer_candidates_index_lists_own_jobs(self):
        self.client.force_login(self.employer_user)

        response = self.client.get(reverse('ai_engine:employer_candidates'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.job.title)
