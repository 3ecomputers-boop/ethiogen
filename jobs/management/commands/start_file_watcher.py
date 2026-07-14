from django.core.management.base import BaseCommand
from jobs.utils.file_watcher import start_file_watcher


class Command(BaseCommand):
    help = 'Start the file system watcher to monitor changes and notify the owner.'

    def handle(self, *args, **options):
        self.stdout.write("Starting file watcher...")
        start_file_watcher()