import os
import time
import threading
from django.conf import settings
from django.core.mail import send_mail
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class NotificationHandler(FileSystemEventHandler):
    """
    Handles file system events and sends notifications to the owner.
    """
    def __init__(self, project_root, owner_email):
        self.project_root = os.path.abspath(project_root)
        self.owner_email = owner_email
        self.last_notification = {}  # rate limiting

    def send_alert(self, event_type, path):
        """Send an email notification with rate limiting (1 per 60 seconds per event type)."""
        now = time.time()
        key = f"{event_type}:{path}"
        if key in self.last_notification and now - self.last_notification[key] < 60:
            return  # rate limit

        subject = f"[MoyaJobs] File System Alert: {event_type}"
        message = f"""
        File system change detected on your Django project.

        Event: {event_type}
        Path: {path}
        Project: {self.project_root}
        Time: {time.ctime()}

        Please verify this action is legitimate.
        """
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.owner_email],
                fail_silently=False,
            )
            self.last_notification[key] = now
        except Exception as e:
            print(f"Failed to send alert: {e}")

    def on_created(self, event):
        if not event.is_directory:
            self.send_alert('CREATED', event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.send_alert('MODIFIED', event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.send_alert('MOVED', f"{event.src_path} → {event.dest_path}")

    def on_deleted(self, event):
        if not event.is_directory:
            self.send_alert('DELETED', event.src_path)


def start_file_watcher():
    """
    Start the file watcher in a background thread.
    """
    project_root = settings.BASE_DIR
    owner_email = getattr(settings, 'OWNER_EMAIL', None)

    if not owner_email:
        print("OWNER_EMAIL not set in settings. File watcher disabled.")
        return

    event_handler = NotificationHandler(project_root, owner_email)
    observer = Observer()
    observer.schedule(event_handler, project_root, recursive=True)
    observer.start()
    print(f"File watcher started on {project_root}. Notifications sent to {owner_email}")

    # Keep the thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("File watcher stopped.")
    observer.join()