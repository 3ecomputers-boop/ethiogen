# Admin Dashboard

The custom admin console lives at **`/admin/`** and replaces Django's default admin landing page for day-to-day staff work. The raw Django admin remains available at **`/django-admin/`** for model-level edits and anything the custom UI does not cover.

## 1. Access and permissions

- Every custom dashboard view is protected by `login_required` + `user_passes_test(lambda u: u.is_staff)`.
- A non-staff user is redirected to the login page.
- A superuser is staff by definition.
- The custom UI uses the same session and CSRF protection as the rest of the site.

To promote a user:

```python
from django.contrib.auth import get_user_model
u = get_user_model().objects.get(username="someone")
u.is_staff = True
u.save()
```

## 2. Layout and theme

The shell is `dashboard/templates/dashboard/base.html`.

### Structure

```
<div class="dash-overlay">              mobile backdrop
<aside class="dash-sidebar">            fixed 230px gradient sidebar
  brand block
  grouped navigation
  signed-in footer + sign out
<div class="dash-main">                 margin-left: 230px
  <header class="dash-header">          sticky page title, date, avatar
  <main>                                messages + page content
```

### Design system

CSS variables in `base.html`:

```css
--primary: #4f46e5;
--primary-dark: #4338ca;
--accent: #f59e0b;
--bg: #f1f5f9;
--card: #ffffff;
--border: #e2e8f0;
--text: #0f172a;
--muted: #64748b;
--sidebar-bg: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
```

Key classes:

| Class | Appearance |
|---|---|
| `dash-card` | White card, 14px radius, layered shadow, hover elevation |
| `dash-kpi` | KPI card with a 4px indigo left accent bar |
| `.dash-kpi .value` / `.label` | Large bold value / uppercase muted label |
| `dash-table` | Header background, row hover, tight padding |
| `badge badge-{green,amber,red,gray,blue}` | Status pills |
| `nav-link` / `nav-link.active` | Sidebar links with indigo active state |
| `save-btn` | Gradient primary button with lift on hover |
| `.field input/textarea/select` | Focus ring in primary colour |

### Responsive behaviour

| Breakpoint | Behaviour |
|---|---|
| `> 768px` | Sidebar fixed at 230px, main content fills the rest |
| `<= 768px` | Sidebar is off-canvas (`translateX(-100%)`), hamburger toggles `.open`, overlay closes it |
| Tables | Horizontally scrollable inside cards |
| KPI grids | `repeat(auto-fit, minmax(150px, 1fr))` |
| Content grids | `repeat(auto-fit, minmax(320px, 1fr))` |

Font stack: `"Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif`. Icons: Bootstrap Icons from jsDelivr. Base CSS: `static/css/tailwind.css`.

### Navigation groups

| Group | Items |
|---|---|
| — | Dashboard |
| People | Users, Job Seekers, Organizations |
| Content | Channel Posts, Applications |
| Billing | Subscriptions, Analytics (`/billing/analytics/` — raw JSON) |
| Settings | Configuration |
| System | All Models, Django Admin (raw), Operator Console (`/admin/dashboard/`) |

## 3. Pages

### 3.1 Dashboard home — `/admin/`

**View:** `dashboard.views.home`

KPI cards:

| KPI | Source |
|---|---|
| Users | `accounts.User.objects.count()` |
| Job Seekers | `JobSeekerProfile.objects.count()` |
| Clients | `ClientProfile.objects.count()` |
| Job Posts | `JobPost.objects.count()` |
| Organizations | `tenants.Organization.objects.count()` |
| Active Tenants | `Organization.status='active'` |
| Channel Posts | `billing.ChannelPost.objects.count()` |
| Published | `ChannelPost.status='published'` |
| Subscriptions | `billing.Subscription.objects.count()` |
| Active Subs | `Subscription.status='active'` |
| Pending Review | `Subscription.status='pending_review'` |
| Applications | `billing.PostApplication.objects.count()` |

Revenue card: sum of `Subscription.amount` for active subscriptions, displayed in ETB.

Recent tables (8 rows each): subscriptions, channel posts, applications, organizations.

### 3.2 Subscriptions — `/admin/subscriptions/`

- Search by username or email (`q`).
- Filter by `status`.
- Paginated 25 per page.
- Columns: ID, user, plan, amount, status, method, created, expires, actions.
- **Approve** calls `billing.services.activate_subscription(...)`.
- **Reject** calls `billing.services.reject_subscription(...)`.
- Both are POST forms with CSRF and redirect back to the list.

Approve is available for any non-active row; reject is available for any non-rejected row.

### 3.3 Channel posts — `/admin/posts/`

- Search by title.
- Filter by `status` and `kind` (job/tender/general).
- Paginated 25 per page.
- **Publish** (`POST /admin/posts/<pk>/publish/`) calls `billing.services.publish_post(post)`, which sends to Telegram and triggers subscriber alerts.

### 3.4 Users — `/admin/users/`

- Ordered by `-date_joined`.
- Search by username or email.
- Paginated 25 per page.
- Read-only list; use `/django-admin/accounts/user/` for edits.

### 3.5 Organizations — `/admin/organizations/`

- Search by name or slug.
- Filter by status.
- Paginated 25 per page.

### 3.6 Job seekers — `/admin/job-seekers/`

- `select_related('user', 'profession')`, newest first.
- Search by username or profile title.
- Paginated 25 per page.

### 3.7 Applications — `/admin/applications/`

- `PostApplication` rows with post and applicant.
- Filter by status (submitted, reviewing, shortlisted, rejected).
- Paginated 25 per page.

### 3.8 Configuration — `/admin/settings/`

The settings page edits the singleton `billing.IntegrationSettings` row. Each card is a **separate form** posting to `/admin/settings/save/` with a hidden `section` value. Saving calls `config.invalidate_cache()`.

| Section | Fields |
|---|---|
| **Telegram Bot & Connection** | `telegram_bot_token` (password input), `telegram_bot_username`, `telegram_channel_id`, `telegram_channel_username`, `telegram_group_id`, `telegram_admin_ids`, `telegram_website_url` |
| **Miniapp & Site** | `site_url`, `notes` |
| **Chapa (Card / Telebirr gateway)** | `chapa_enabled`, `chapa_public_key`, `chapa_secret_key`, `chapa_api_base`, `chapa_auto_approve`, `chapa_webhook_url` |
| **Telebirr (manual transfer)** | `telebirr_enabled`, `telebirr_name`, `telebirr_phone`, `telebirr_api_base`, `telebirr_api_key`, `telebirr_merchant_id`, `telebirr_return_url` |
| **Bank** | `bank_enabled`, `bank_name`, `bank_account_name`, `bank_account_number` |
| **Subscription** | `currency`, `subscription_price`, `subscription_days`, `payment_instructions` |
| **Branding** | `logo_wordmark`, `logo_show_caption`, `logo_height_px` |
| **Facebook** | `facebook_enabled`, `facebook_page_id`, `facebook_page_name`, `facebook_page_access_token`, `facebook_api_version`, `facebook_default_link` |
| **Diagnostics** | Read-only `config.configuration_report()` table |

The diagnostics panel performs **no network calls**. It reports the active configuration source and whether each value is set. Use `manage.py verify_telegram` for live Telegram checks.

> **Logo uploads:** the branding card edits the wordmark, caption, and height. To upload `logo_image` / `favicon_image`, use `/django-admin/billing/integrationsettings/` (or the raw admin form). The uploaded logo is reused across the site.

### 3.9 All Models — `/admin/admin-models/`

Builds a grouped list from `admin.site._registry`:

- One card per Django app.
- One row per registered model: plural verbose name, live row count, and a link to `/django-admin/<app_label>/<model_name>/`.
- Counts use `model.objects.count()` when the model has a default manager.

Use this as the map of everything manageable in the raw admin.

## 4. Raw Django admin — `/django-admin/`

The default admin is still fully available. It is the place to:

- Edit any model not exposed by the custom console.
- Upload branding images.
- Manage users, roles, permissions, and groups.
- Inspect alert deliveries, tenant audit logs, and integration settings.
- Use `django-admin` actions, filters, date hierarchy, and search fields configured in each app's `admin.py`.

Notable registrations:

| App | Models |
|---|---|
| `accounts` | `User`, `Role` |
| `jobs` | Most portal models (see `jobs/admin.py` and `jobs/admin_missing.py`) |
| `billing` | `IntegrationSettings`, `ChannelPost`, `Subscription`, `AlertDelivery`, `PostApplication` |
| `social` | `Connection`, `Post`, `PostLike`, `PostComment`, `SavedJob`, `Notification` |
| `tenants` | `Organization`, `Membership`, `Invitation`, `TenantPlan`, `TenantSubscription`, `TenantAuditLog` |
| `recruitment` | `Application` |
| `freelancer` | `Skill`, `FreelancerProfile`, `JobPosting`, `Bid` |
| `employers` | `Employer` |
| `borker_network` | `Broker`, `Deal`, `Payout`, `Task` |

`tenants/apps.py` also installs a custom `/django-admin/ecosystem/` page via `tenants/ecosystem.py`.

## 5. Legacy staff dashboard — `/admin/dashboard/`

`/admin/dashboard/` maps to `jobs.views.staff_dashboard`, not the custom console. It predates the custom dashboard and is kept for compatibility. The custom console is `/admin/` (no suffix).

## 6. Static files and styling

The console depends on:

- `static/css/tailwind.css` (from `STATICFILES_DIRS`)
- Bootstrap Icons CDN
- Inline theme CSS in `base.html`

When `DEBUG=False`, the project adds an explicit route:

```python
path('static/<path:path>', serve, {'document_root': BASE_DIR / 'static'})
```

This keeps the dashboard styled on a single-server deployment. For a normal production setup, run `collectstatic` and let Nginx/Apache/LiteSpeed serve `/static/` from `staticfiles/`.

If the console looks unstyled:

1. Confirm `static/css/tailwind.css` exists.
2. Confirm the browser can GET `/static/css/tailwind.css` (200, `text/css`).
3. Check that Bootstrap Icons is not blocked by CSP or the network.
4. Run `python manage.py collectstatic --noinput` if serving from `staticfiles/`.

## 7. Extending the console

### Add a page

1. Add a view in `dashboard/views.py`, decorated with `_wrap` (applies login + staff checks).
2. Use `_ctx(request, ...)` to get counts, `now`, and `user`.
3. Add a template under `dashboard/templates/dashboard/`.
4. Register the route in `dashboard/urls.py`.
5. Add a nav link in `dashboard/templates/dashboard/base.html` with an active-state check:

```django
<a href="{% url 'dashboard:my_page' %}"
   class="nav-link {% if request.resolver_match.url_name == 'my_page' %}active{% endif %}">
  <i class="bi bi-star"></i> My Page
</a>
```

### Add a settings section

1. Add the field names to `SECTION_FIELDS` in `dashboard/views.py`.
2. Add a card to `dashboard/templates/dashboard/settings.html` with `<input type="hidden" name="section" value="my_section">`.
3. Add the model fields in `billing.models.IntegrationSettings` and migrate.
4. Add accessors in `billing/config.py` so the rest of the app reads the value through the cache.

### Add an action

Use `@require_POST` and a CSRF-protected form. Redirect back to the list with `redirect('dashboard:...')`.

## 8. Operational notes and limitations

- The console is staff-only and server-rendered; there is no JavaScript framework.
- List pages are paginated at 25 rows.
- Search uses `icontains` and does not use full-text indexes.
- The "Analytics" nav item opens raw JSON, not a chart page.
- The custom console does not replace model permissions: staff can see pages, but raw-admin edits still follow Django's model permissions.
- Approving a subscription sends a Telegram notification if the user has a resolvable chat ID. If Telegram is unreachable, approval still succeeds and the failure is logged.
- The settings page shows secrets in password inputs but does not mask them server-side; restrict staff access accordingly.

## 9. Quick verification checklist

```powershell
python manage.py check
python manage.py runserver 127.0.0.1:8000
```

| Check | Expected |
|---|---|
| `/admin/` unauthenticated | Redirect to login |
| `/admin/` as staff | KPI cards and recent tables |
| `/admin/settings/` | All cards render, diagnostics populated |
| Save one section | Success message; value persists after reload |
| `/admin/admin-models/` | Every app/model with counts and working links |
| `/django-admin/` | Styled Django admin |
| Narrow the window | Sidebar collapses, overlay works |
| `/billing/analytics/` as staff | JSON with `subscriptions`, `revenue_active_etb`, `posts`, `applications`, `alerts` |
