# Social Features (LinkedIn-style Layer)

The `social` app adds a professional-network layer on top of the job portal: a feed, connections, saved jobs, notifications, and direct messages. It is intentionally lightweight and server-rendered.

## 1. At a glance

| Feature | URL | Model(s) |
|---|---|---|
| Professional feed | `/social/` | `Post`, `PostLike`, `PostComment` |
| Connections | `/social/connections/` | `Connection` |
| Saved jobs | `/social/saved-jobs/` | `SavedJob` → `jobs.JobPost` |
| Notifications | `/social/notifications/` | `Notification` |
| Direct messages | `/social/inbox/` | `jobs.Message` |
| Admin management | `/django-admin/social/...` | All of the above |

All social pages require login (`@login_required`).

## 2. Models

### `Connection`

A directed request from one user to another.

| Field | Type | Notes |
|---|---|---|
| `from_user` | FK `accounts.User` | Sender; related name `sent_connections` |
| `to_user` | FK `accounts.User` | Recipient; related name `received_connections` |
| `status` | char | `pending` (default), `accepted`, `rejected` |
| `created_at` | datetime | auto |
| `updated_at` | datetime | auto |

Constraints: `unique_together = ('from_user', 'to_user')`; newest first.

### `Post`

| Field | Type | Notes |
|---|---|---|
| `author` | FK user | `related_name='posts'` |
| `content` | text | Required in the view (trimmed, non-empty) |
| `image` | image | Optional; upload to `social/posts/` (no UI upload yet) |
| `created_at`, `updated_at` | datetime | Newest first |

Properties: `like_count`, `comment_count`.

### `PostLike`

Unique like per `(post, user)`. Toggling deletes the row.

### `PostComment`

`post`, `author`, `content`, `created_at`; ordered oldest first.

### `SavedJob`

Unique `(user, job)` pair. `job` is `jobs.JobPost` with related name `saved_by`.

### `Notification`

| Field | Type | Notes |
|---|---|---|
| `user` | FK user | Recipient |
| `type` | char | `connection`, `like`, `comment`, `message`, `job`, `system` |
| `title` | char(255) | Short headline |
| `body` | text | Optional detail |
| `link` | char(255) | Relative URL to open |
| `is_read` | bool | Indexed |
| `created_at` | datetime | Newest first |

## 3. Routes and views

| Method | Route | View | Behaviour |
|---|---|---|---|
| GET | `/social/` | `feed` | Last 50 posts with author, likes, comments |
| POST | `/social/` | `feed` | Creates a post from `content`; redirects to feed |
| GET | `/social/like/<pk>/` | `like_post` | Toggles like; returns JSON `{likes: n}` for AJAX, otherwise redirects |
| POST | `/social/comment/<pk>/` | `comment_post` | Creates a comment; notifies the post author; redirects |
| GET | `/social/connections/` | `connections` | Pending-in, pending-out, accepted lists |
| GET | `/social/connect/<user_id>/` | `connect` | Creates a pending request; notifies recipient |
| POST | `/social/connections/<pk>/accept/` | `connection_action` | Accepts; notifies sender |
| POST | `/social/connections/<pk>/reject/` | `connection_action` | Rejects |
| GET | `/social/saved-jobs/` | `saved_jobs` | Lists saved jobs |
| GET/POST | `/social/save-job/<job_id>/` | `save_job` | Creates a saved-job row; redirects |
| GET/POST | `/social/unsave-job/<job_id>/` | `unsave_job` | Deletes the row; redirects |
| GET | `/social/notifications/` | `notifications` | Marks all unread as read, then lists |
| GET/POST | `/social/inbox/` | `inbox` | Lists last 50 messages; POST sends one |

### Feed flow

```
GET /social/
  → Post.objects.select_related('author').prefetch_related('likes','comments')[:50]
  → render social/feed.html

POST /social/  (content)
  → Post.objects.create(author=request.user, content=content)
  → redirect /social/
```

Likes are toggles:

```
PostLike.get_or_create(post, user)
  created → liked
  existing → delete (unlike)
```

Comments notify the author unless the commenter is the author:

```python
Notification.objects.create(
    user=post.author,
    type='comment',
    title='New comment on your post',
    body=content[:120],
    link=f'/social/feed/#post-{post.pk}',
)
```

### Connection flow

```
A opens /social/connect/<B id>/
  → Connection(from_user=A, to_user=B, status=pending)
  → Notification to B

B opens /social/connections/
  → sees pending_in
  → POST accept/reject
  → status changes; A is notified on accept

Both see the row in `accepted` once accepted, filtered by
Q(from_user=user) | Q(to_user=user)
```

### Saved jobs flow

```
/social/save-job/<job_id>/   → SavedJob.get_or_create(user, job)
/social/unsave-job/<job_id>/ → SavedJob.filter(user, job).delete()
/social/saved-jobs/          → SavedJob.filter(user).select_related('job')
```

### Notifications

- Created on: connection request, connection acceptance, comment, new message.
- The list page marks **all** unread notifications as read on load.
- There is no badge counter in the social header yet; add one with `Notification.objects.filter(user=request.user, is_read=False).count()`.

### Inbox

- Uses the existing `jobs.Message` model (sender, recipient, message, is_read, timestamp).
- Lists messages where the user is sender or recipient, newest first, limit 50.
- Sending requires the **recipient's numeric user ID** (see limitations).
- A `message` notification is created for the recipient.

## 4. Templates and UI

Templates live in `social/templates/social/`:

| File | Purpose |
|---|---|
| `base.html` | Minimal top-nav shell, card/button/avatar styles |
| `feed.html` | Composer, post cards, like/comment, comments list |
| `connections.html` | Pending-in, accepted, pending-out |
| `saved_jobs.html` | Saved job cards with remove |
| `notifications.html` | Notification list with unread accent |
| `inbox.html` | Send form and message list |

`base.html` loads `static/css/tailwind.css` and Bootstrap Icons. It is deliberately separate from the staff dashboard shell because social pages are user-facing, not staff-facing.

Navigation in the social shell: Feed, Network, Messages, Saved Jobs, Notifications, Sign out.

## 5. Admin management

All social models are registered in `social/admin.py`:

| Model | List display | Filters/search |
|---|---|---|
| `Connection` | from, to, status, created | status; usernames |
| `Post` | author, content, created | author/content search |
| `PostLike` | post, user, created | — |
| `PostComment` | post, author, content, created | — |
| `SavedJob` | user, job, created | — |
| `Notification` | user, type, title, is_read, created | type, is_read |

Use `/django-admin/social/...` to moderate content, delete spam, or inspect notifications. The custom dashboard does not yet have a social moderation page.

## 6. Database

Migration: `social/migrations/0001_initial.py`.

Apply with:

```bash
python manage.py migrate social
```

The app is registered as `social` in `INSTALLED_APPS` and uses `SocialConfig` (`Social / LinkedIn features`).

## 7. Permissions and privacy

| Action | Rule |
|---|---|
| View feed | Any authenticated user |
| Create post | Any authenticated user |
| Like/comment | Any authenticated user |
| Connect | Any authenticated user, not yourself |
| Accept/reject | Only the recipient of the request |
| Save job | Any authenticated user |
| View notifications | Only your own |
| View inbox | Only messages you sent or received |
| Send message | Any authenticated user, to a valid user ID |

There is no block/mute, reporting, or content visibility model yet.

## 8. Current limitations and hardening backlog

The layer is functional but intentionally minimal. Known gaps:

1. **GET actions** — `like_post`, `connect`, `save_job`, and `unsave_job` are GET routes that mutate data. Convert them to POST forms with CSRF to prevent prefetch/link-triggered changes.
2. **No reverse-connection check** — A→B and B→A can both exist as separate pending rows. Consider merging or rejecting duplicates.
3. **Feed is global** — it shows the latest 50 posts from everyone, not just connections. Add a "following/connections" filter if needed.
4. **No pagination** — the feed is capped at 50; add a `Paginator`.
5. **Inbox needs a numeric user ID** — replace the free-text recipient field with a user picker or a "Message" button on profiles/connections.
6. **No unread badge** — notifications are marked read on page load, so the header cannot show a count afterwards. Add a context processor or a dedicated count endpoint.
7. **No like notifications** — the `like` notification type exists but is not created in `like_post`.
8. **No image upload UI** — `Post.image` exists but the form only posts text.
9. **No edit/delete UI** — posts and comments can only be removed in Django admin.
10. **No moderation tools** — no report/flag model.
11. **No tests** — `social` has no test suite yet.
12. **No real-time updates** — everything is request/response; no websockets or polling.

Recommended next steps, in order:

1. Convert mutations to POST.
2. Add a user picker for messages and a "Message" button on connections.
3. Add pagination and connection-filtered feed.
4. Add unread notification counts to the social header.
5. Add post/comment delete and edit for authors and staff.
6. Add tests for toggle-like, accept/reject authorization, and notification creation.

## 9. Quick test plan

```bash
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

1. Sign in as user A; open `/social/` and create a post.
2. Open `/social/like/<post_id>/`; the count increments. Open again; it decrements.
3. Add a comment as user B; user A receives a notification.
4. Sign in as A; open `/social/connect/<B id>/`.
5. Sign in as B; open `/social/connections/` and accept.
6. Both users see each other under accepted connections.
7. Save a job from `/social/save-job/<job_id>/`; verify it appears at `/social/saved-jobs/`.
8. Send a message from `/social/inbox/` using the recipient's numeric user ID.
9. Check `/django-admin/social/notification/` for the created rows.

## 10. Example: create a notification from another app

```python
from social.models import Notification

Notification.objects.create(
    user=some_user,
    type='job',
    title='New job matching your skills',
    body='Senior Django Developer at Acme',
    link='/jobs/42/',
)
```

## 11. Example: query social data

```python
from social.models import Connection, Post, Notification

# Accepted connections for a user
from django.db.models import Q
connections = Connection.objects.filter(status='accepted').filter(
    Q(from_user=user) | Q(to_user=user)
)

# Latest posts with counts
posts = Post.objects.select_related('author').prefetch_related('likes', 'comments')[:20]

# Unread count
unread = Notification.objects.filter(user=user, is_read=False).count()
```
