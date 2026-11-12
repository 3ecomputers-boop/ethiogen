from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Connection, Post, PostLike, PostComment, SavedJob, Notification


@login_required
def feed(request):
    posts = Post.objects.select_related('author').prefetch_related('likes', 'comments').all()[:50]
    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        if content:
            Post.objects.create(author=request.user, content=content)
            return redirect('social:feed')
    return render(request, 'social/feed.html', {'posts': posts})


@login_required
def like_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    like, created = PostLike.objects.get_or_create(post=post, user=request.user)
    if not created:
        like.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'likes': post.like_count})
    return redirect('social:feed')


@login_required
def comment_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    content = request.POST.get('content', '').strip()
    if content:
        PostComment.objects.create(post=post, author=request.user, content=content)
        if post.author != request.user:
            Notification.objects.create(user=post.author, type='comment', title='New comment on your post', body=content[:120], link=f'/social/feed/#post-{post.pk}')
    return redirect('social:feed')


@login_required
def connections(request):
    pending_in = Connection.objects.filter(to_user=request.user, status=Connection.STATUS_PENDING)
    pending_out = Connection.objects.filter(from_user=request.user, status=Connection.STATUS_PENDING)
    from django.db import models as _m
    accepted = Connection.objects.filter(status=Connection.STATUS_ACCEPTED).filter(
        _m.Q(from_user=request.user) | _m.Q(to_user=request.user)
    )
    return render(request, 'social/connections.html', {
        'pending_in': pending_in, 'pending_out': pending_out, 'accepted': accepted,
    })


@login_required
def connect(request, user_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    target = get_object_or_404(User, pk=user_id)
    if target == request.user:
        return redirect('social:connections')
    conn, created = Connection.objects.get_or_create(from_user=request.user, to_user=target)
    if created:
        Notification.objects.create(user=target, type='connection', title=f'{request.user.username} wants to connect', link='/social/connections/')
    return redirect('social:connections')


@login_required
def connection_action(request, pk, action):
    conn = get_object_or_404(Connection, pk=pk, to_user=request.user)
    if action == 'accept':
        conn.status = Connection.STATUS_ACCEPTED
        conn.save()
        Notification.objects.create(user=conn.from_user, type='connection', title=f'{request.user.username} accepted your connection', link='/social/connections/')
    elif action == 'reject':
        conn.status = Connection.STATUS_REJECTED
        conn.save()
    return redirect('social:connections')


@login_required
def saved_jobs(request):
    saved = SavedJob.objects.filter(user=request.user).select_related('job')
    return render(request, 'social/saved_jobs.html', {'saved': saved})


@login_required
def save_job(request, job_id):
    from jobs.models import JobPost
    job = get_object_or_404(JobPost, pk=job_id)
    SavedJob.objects.get_or_create(user=request.user, job=job)
    return redirect('social:saved_jobs')


@login_required
def unsave_job(request, job_id):
    from jobs.models import JobPost
    job = get_object_or_404(JobPost, pk=job_id)
    SavedJob.objects.filter(user=request.user, job=job).delete()
    return redirect('social:saved_jobs')


@login_required
def notifications(request):
    notifs = Notification.objects.filter(user=request.user)
    notifs.filter(is_read=False).update(is_read=True)
    return render(request, 'social/notifications.html', {'notifications': notifs})


@login_required
def inbox(request):
    from jobs.models import Message
    msgs = Message.objects.filter(recipient=request.user) | Message.objects.filter(sender=request.user)
    msgs = msgs.order_by('-timestamp')[:50]
    if request.method == 'POST':
        recipient_id = request.POST.get('recipient')
        content = request.POST.get('message', '').strip()
        if recipient_id and content:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            recipient = get_object_or_404(User, pk=recipient_id)
            Message.objects.create(sender=request.user, recipient=recipient, message=content)
            Notification.objects.create(user=recipient, type='message', title=f'New message from {request.user.username}', link='/social/inbox/')
            return redirect('social:inbox')
    return render(request, 'social/inbox.html', {'messages': msgs})