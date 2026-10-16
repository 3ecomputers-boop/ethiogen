import os
import tempfile
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
import yt_dlp
import whisper
from deep_translator import GoogleTranslator
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Download YouTube news audio, transcribe to Amharic, and post to Telegram'

    def add_arguments(self, parser):
        parser.add_argument('--url', type=str, required=True, help='YouTube video URL')
        parser.add_argument('--no-translate', action='store_true', help='Skip translation (assume audio is already Amharic)')
        parser.add_argument('--model', type=str, default=getattr(settings, 'WHISPER_MODEL', 'base'),
                            help='Whisper model size (tiny/base/small/medium/large)')

    def handle(self, *args, **options):
        url = options['url']
        model_name = options['model']
        no_translate = options['no_translate']

        self.stdout.write(f'Processing: {url}')

        audio_path = self.download_audio(url)
        if not audio_path:
            self.stderr.write('Failed to download audio.')
            return

        self.stdout.write('Transcribing...')
        transcript = self.transcribe_audio(audio_path, model_name)
        
        if os.path.exists(audio_path):
            os.remove(audio_path)

        if not transcript:
            self.stderr.write('Transcription failed.')
            return

        self.stdout.write(f'Original transcript: {transcript[:200]}...')

        amharic_text = transcript
        if not no_translate:
            self.stdout.write('Translating to Amharic...')
            amharic_text = self.translate_to_amharic(transcript)
            if not amharic_text:
                self.stderr.write('Translation failed. Using original transcript.')
                amharic_text = transcript

        self.stdout.write('Sending to Telegram...')
        success = self.send_to_telegram(amharic_text, url)
        if success:
            self.stdout.write(self.style.SUCCESS('Done!'))
        else:
            self.stderr.write('Telegram send failed.')

    def download_audio(self, url):
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
                output_template = tmp.name.replace('.mp3', '')
                
                ydl_opts = {
                    'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'outtmpl': output_template,
                    'quiet': True,
                    
                    # Try tv_embedded client - often bypasses bot checks
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['tv_embedded'],
                            'player_skip': ['webpage', 'configs', 'js'],
                        }
                    },
                    
                    'sleep_requests': 2,
                    'sleep_interval': 2,
                    'nocheckcertificate': True,
                }

    def transcribe_audio(self, audio_path, model_name):
        try:
            model = whisper.load_model(model_name)
            result = model.transcribe(audio_path)
            return result['text']
        except Exception as e:
            logger.error(f'Transcription error: {e}')
            return None

    def translate_to_amharic(self, text):
        try:
            translator = GoogleTranslator(source='auto', target='am')
            return translator.translate(text)
        except Exception as e:
            logger.error(f'Translation error: {e}')
            return None

    def send_to_telegram(self, text, url):
        try:
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            message = f"📰 *News Transcript (Amharic)*\n\n{text}\n\n🔗 [Watch on YouTube]({url})"
            bot.send_message(
                chat_id=settings.TELEGRAM_CHAT_ID,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return True
        except Exception as e:
            logger.error(f'Telegram error: {e}')
            return False