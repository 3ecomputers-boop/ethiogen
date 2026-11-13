# User Guide

This is the non-technical guide for people using the Ethiogen site: job seekers, employers, subscribers, and staff.

## 1. Who can do what

| Role | Main abilities |
|---|---|
| Visitor | Browse the home page, jobs, talents, and public pages |
| Job seeker | Create a profile, browse jobs, apply, save jobs, post in the feed, connect, message |
| Employer / client | Create a company profile, post jobs, review applicants, manage a workspace |
| Subscriber | Unlock channel posts and apply from Telegram |
| Staff | Use the custom admin console and raw Django admin |
| Superuser | Everything, including the tenant operator console |

## 2. Creating an account

### Job seeker registration

1. Open the home page (`/`) and use the **Join as Talent / Sign Up** form.
2. Fill in your details and submit. The form posts to the registration endpoint (`/register/job-seeker/`), which is API-style and expects a POST — do not open that URL directly in the browser.
3. Check your email for the OTP.
4. Enter the OTP at `/verify-otp/`.
5. Complete your professional profile.

If the email does not arrive, use **Resend OTP** at `/resend-otp/`. In development, the OTP may be printed to the console if email delivery fails.

### Employer registration

1. Use the employer registration form on the home page (posts to `/api/register/employer/`).
2. Provide company name, your name, email, phone, and password.
3. A `ClientProfile` is created for your company.
4. Sign in at `/accounts/login/`.

### Standard login

Go to `/accounts/login/` and enter your username/email and password. After login you are redirected based on your role:

- Staff → staff dashboard
- Job seeker → seeker dashboard (or OTP if unverified)
- Employer → employer dashboard
- No profile → profile setup

## 3. Job seeker basics

### Dashboard

`/dashboard/` is your home base. It links to your profile, jobs, applications, and messages.

### Create or edit your profile

- Create: `/profile/create/`
- View a profile: `/profile/<id>/`
- Browse other professionals: `/browse/`

A strong profile includes:

- Professional title
- Bio
- City/location
- Skills
- Years of experience
- Hourly rate or price per unit
- Profile picture
- Portfolio/LinkedIn links
- Certifications
- CV/resume upload

Verification (`is_verified`) is granted by staff and improves trust.

### Browse jobs and contact employers

1. Open `/jobs/` to see listings and use the filters.
2. Open a job at `/jobs/<id>/` for details.
3. Use the message form on the job page to contact the poster.
4. Save a channel job for later from the social layer (`/social/save-job/<job_id>/`).

Formal application forms live in the recruitment module (`/recruitment/<id>/apply/`) and in the Telegram channel (**Apply Now** on a published post, which requires an active subscription). The job seeker dashboard currently shows profile completion and navigation; it does not yet provide a full application tracker.

### Recommended jobs

Open `/matches/` or use **Recommended** on the dashboard. The page ranks approved jobs against your profile and shows:

- a 0–100 match score,
- reasons such as matching skills, location, and experience,
- gaps such as missing skills or an unverified profile,
- a score breakdown by signal.

Scores are generated from your profile data. They are a matching aid, not a guarantee of shortlisting. Keep your title, skills, city, experience, and CV up to date to improve results.

### Reviews

After a completed job, reviews can be created at `/jobs/<job_id>/review/<provider_id>/`. Ratings contribute to a professional's average rating.

## 4. Employer basics

### Company profile

`/client/profile/` — company name, location, phone, website, and bio. Staff can verify the company.

### Employer dashboard

`/employer-dashboard/` — shortlists, hiring, and checkout.

### Post a job

- `/jobs/add/` — add a job request.
- `/client/jobs/create/` — create a job request from the client area.
- `/billing/api/employer/post-job/` — API used by the mini app to publish directly to the Telegram channel.

Employer job posting requires:

1. An employer account (`ClientProfile` or active workspace membership).
2. An active subscription.
3. A workspace plan with remaining job-post quota (when the post belongs to an organization).

### Review applicants

- `/admin/applications/` (staff dashboard) shows `PostApplication` rows.
- Employer API: `/billing/api/employer/applications/`.
- Update status to `reviewing`, `shortlisted`, or `rejected`; the applicant is notified by Telegram/email when possible.

### Rank candidates

Open `/matches/candidates/` or use **AI Candidates** in the employer dashboard. Choose one of your jobs to see active job seekers ordered by match score. Each candidate card explains the score and shows gaps. Only the job owner and staff can view this page; other users receive `403`.

Candidate rankings are decision support. Review applications, interviews, and references before hiring. The JSON equivalent is `/matches/api/jobs/<job_id>/candidates/`.

### Workspaces

`/tenants/workspaces/` — create or join a company workspace. Members can have roles (owner/admin/recruiter/viewer), invite colleagues, and manage billing. Invitations arrive by email and are accepted at `/tenants/invitations/<token>/`.

## 5. Social network

Sign in and open `/social/`.

### Feed

- Write an update in the composer and press **Post**.
- Like a post with the thumbs-up link.
- Comment using the field under each post.
- Comments notify the post author.

### Connections

- Open `/social/connections/` to see requests.
- Connect with someone by visiting `/social/connect/<user_id>/`.
- Accept or ignore pending requests.
- Accepted connections appear under **Your connections**.

### Saved jobs

- Save from `/social/save-job/<job_id>/`.
- View at `/social/saved-jobs/`.
- Remove with **Remove** (unsave).

### Notifications

`/social/notifications/` shows connection, comment, message, job, and system notifications. Opening the page marks all as read.

### Messages

`/social/inbox/` lists recent messages and lets you send one.

To send, enter the recipient's **numeric user ID** (find it in the admin user list) and the message. This is a known limitation; a user picker is planned.

## 6. Subscriptions and the Telegram channel

### What a subscription unlocks

An active subscription lets you apply to job and tender posts published in the Telegram channel. It also controls whether you receive job alerts.

### How to subscribe

1. Open a post in the Telegram channel.
2. Tap **Subscribe**.
3. Choose a payment method:
   - **Card / Telebirr via Chapa** — pay online; activation is automatic when Chapa confirms.
   - **Telebirr transfer** — send to the shown phone, then upload the receipt.
   - **Bank transfer** — send to the shown account, then upload the receipt.
4. For manual payments, tap **I Have Paid — Upload Receipt**, then send a clear photo/screenshot. Put the transaction reference in the caption.
5. Wait for staff approval. You receive a Telegram message when approved.

### Applying to a post

1. Tap **Apply Now** on a channel post.
2. If you are not subscribed, you are prompted to subscribe.
3. Once subscribed, your application is recorded and the employer is notified.

### Alerts

Choose how you hear about new posts:

- **Every new post, immediately**
- **One daily digest** (choose the hour)
- **Only posts matching my profile**
- Mute alerts without cancelling

Manage these through the bot or the alert-preference API (`/billing/api/alerts/preferences/`).

### Renewals and expiry

- Plans have an expiry date.
- `renewal_reminders` sends reminders before expiry and marks lapsed plans as expired.
- Renew by subscribing again; approval extends access from the activation date.

## 7. Staff guide

### Access

Staff sign in at `/accounts/login/` and use:

- `/admin/` — custom console
- `/django-admin/` — raw Django admin

### Daily tasks

| Task | Where |
|---|---|
| Review payments | `/admin/subscriptions/` → Approve/Reject |
| Publish a post to Telegram | `/admin/posts/` → Publish |
| Check platform KPIs | `/admin/` |
| Find a user | `/admin/users/` |
| Review job seekers | `/admin/job-seekers/` |
| Review applications | `/admin/applications/` |
| Manage organizations | `/admin/organizations/` |
| Configure integrations | `/admin/settings/` |
| Find any model | `/admin/admin-models/` |

### Approving a subscription

1. Open `/admin/subscriptions/`.
2. Filter by **Pending review**.
3. Open the receipt in the raw admin if needed (`/django-admin/billing/subscription/`).
4. Click **Approve** or **Reject**.
5. The user is notified by Telegram and email when possible.

### Publishing a post

1. Create the post in `/django-admin/billing/channelpost/add/`.
2. Set kind, title, body, company, location, salary, deadline, and buttons.
3. Save.
4. Open `/admin/posts/` and click **Publish**.
5. Check the status: `published` or `failed` with an error.

### Moderation

Use `/django-admin/social/post/` and `/django-admin/social/postcomment/` to remove inappropriate content. There is no in-app report queue yet.

## 8. Notifications and email

- In-app notifications: `/social/notifications/`
- Telegram notifications: subscription approval/rejection, application status, alerts
- Email: OTP, application received, receipt received, approval/rejection, expiry reminders

Email failures are logged but do not block the underlying action.

## 9. Common user questions

**I registered but cannot log in.**
Your account may be inactive until OTP verification. Complete `/verify-otp/` or ask staff to verify you.

**I forgot my password.**
Ask an administrator to run `python manage.py changepassword <username>`. Self-service reset is not configured.

**I paid but my subscription is still pending.**
Manual payments require staff review. Check that you uploaded a clear receipt with a reference. Staff can approve from `/admin/subscriptions/`.

**I cannot apply to a post.**
You need an active subscription. Tap Subscribe and complete payment.

**I did not receive a Telegram message.**
The bot can only DM users who have started it. Open the bot and press Start.

**My feed post is missing.**
The feed shows the latest 50 posts. Check `/django-admin/social/post/` if you are staff.

**How do I message someone?**
Use `/social/inbox/` with their numeric user ID. A user picker is planned.

**How do I save a job?**
Open `/social/save-job/<job_id>/`; view saved jobs at `/social/saved-jobs/`.

**How do I change the language?**
Use the language switch on the public site (`/language/<lang>/`) or the bot's settings.

## 10. Support checklist

When contacting support, include:

- Your username and email
- The page or command you used
- What you expected vs what happened
- A screenshot (for payment or UI issues)
- The approximate time of the issue
- For payments: amount, method, and transaction reference
