import os
import json
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from pathlib import Path

class Command(BaseCommand):
    help = 'Scrapes ethiojobs.net JSON data and posts updates to Telegram'

    def add_arguments(self, parser):
        parser.add_argument('--url', type=str, required=True)
        parser.add_argument('--groups', nargs='+', type=str, required=True)
        parser.add_argument('--selector', type=str, required=False, help='Legacy argument, ignored for Next.js sites')
        parser.add_argument('--force', action='store_true')

    def handle(self, *args, **options):
        url = options['url']
        groups = options['groups']
        force_post = options.get('force', False)
        
        token = os.getenv('ETHIOGEN_BOT_TOKEN')
        if not token:
            self.stdout.write(self.style.ERROR('❌ ETHIOGEN_BOT_TOKEN environment variable is not set!'))
            return
        
        # Path to tracking file
        tracking_file = Path(__file__).parent.parent.parent / 'posted_jobs.json'
        
        # Load previously posted jobs
        posted_jobs = self.load_posted_jobs(tracking_file)
        
        self.stdout.write(self.style.SUCCESS(f'🔄 Fetching data from: {url}'))
        self.stdout.write(f'📊 Found {len(posted_jobs)} previously posted jobs in tracking file')
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        
        try:
            # 1. Fetch the HTML
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            # 2. Parse and find the Next.js data
            soup = BeautifulSoup(response.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            
            if not script:
                self.stdout.write(self.style.ERROR('❌ Could not find __NEXT_DATA__ script tag.'))
                return
            
            data = json.loads(script.string)
            jobs_wrapper = data.get('props', {}).get('pageProps', {}).get('jobs', {})
            jobs_list = jobs_wrapper.get('data', [])
            
            self.stdout.write(f'📊 Found {len(jobs_list)} jobs on the website.')
            
            if not jobs_list:
                self.stdout.write(self.style.WARNING('⚠️ No jobs found in the data array.'))
                return
            
            # 3. Filter out already posted jobs (unless --force is used)
            if force_post:
                self.stdout.write(self.style.WARNING('⚠️ --force flag detected. Posting all jobs regardless of tracking.'))
                jobs_to_post = jobs_list[:10]
            else:
                jobs_to_post = [
                    job for job in jobs_list 
                    if job.get('slug') not in posted_jobs
                ][:5]  # Limit to 5 new jobs per run
                
                self.stdout.write(f'🆕 Found {len(jobs_to_post)} NEW jobs to post (skipping {len(jobs_list) - len(jobs_to_post)} already posted)')
            
            if not jobs_to_post:
                self.stdout.write(self.style.SUCCESS('✅ No new jobs to post. All jobs have already been sent.'))
                return
            
            posted_count = 0
            
            for job in jobs_to_post:
                title = job.get('title', 'Unknown Title')
                location_type = job.get('location_type', 'Unknown Location')
                date_published = job.get('date_published', '')
                date_expiry = job.get('date_expiry', '')
                slug = job.get('slug', '')
                
                # Safely extract company name
                company_data = job.get('company', {})
                if isinstance(company_data, dict):
                    company_name = company_data.get('name', 'Unknown Company')
                else:
                    company_name = str(company_data) if company_data else 'Unknown Company'
                
                # Format dates
                published_str = date_published[:10] if date_published else 'N/A'
                deadline_str = date_expiry[:10] if date_expiry else 'N/A'
                
                # Clean and truncate description
                raw_description = job.get('description', '')
                if raw_description:
                    clean_desc = BeautifulSoup(raw_description, 'html.parser').get_text(separator=' ', strip=True)
                    description_str = (clean_desc[:180] + '...') if len(clean_desc) > 180 else clean_desc
                else:
                    description_str = 'No description provided.'
                
                # Format the message
                message = (
                    f"📢 *New Job Opportunity!*\n\n"
                    f"💼 *Title:* {title}\n"
                    f"🏢 *Company:* {company_name}\n"
                    f"📍 *Location:* {location_type}\n"
                    f"⏰ *Deadline:* {deadline_str}\n\n"
                    f"📝 *Description:*\n{description_str}\n\n"
                    f"ℹ️ *To Apply:* Please visit the company's official career page for application instructions."
                )
                
                # Send to all groups
                success_in_any_group = False
                for group_id in groups:
                    try:
                        send_url = f'https://api.telegram.org/bot{token}/sendMessage'
                        payload = {
                            'chat_id': group_id,
                            'text': message,
                            'parse_mode': 'Markdown',
                            'disable_web_page_preview': True
                        }
                        r = requests.post(send_url, json=payload, timeout=10)
                        result = r.json()
                        
                        if result.get('ok'):
                            self.stdout.write(self.style.SUCCESS(f'✅ Successfully posted "{title}" to group {group_id}'))
                            success_in_any_group = True
                        else:
                            self.stdout.write(self.style.ERROR(f'❌ Failed to post to {group_id}: {result.get("description")}'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'❌ Error sending to {group_id}: {str(e)}'))
                
                # Track this job as posted (only if successfully sent to at least one group)
                if success_in_any_group and slug:
                    posted_jobs.add(slug)
                    posted_count += 1
            
            # Save updated tracking file
            self.save_posted_jobs(tracking_file, posted_jobs)
            
            if posted_count > 0:
                self.stdout.write(self.style.SUCCESS(f'\n🎉 Done! Posted {posted_count} new job(s) to the channel(s).'))
                self.stdout.write(f'📝 Total tracked jobs: {len(posted_jobs)}')
            else:
                self.stdout.write(self.style.WARNING('\n⚠️ No jobs were posted.'))
                
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'💥 Network error: {e}'))
        except json.JSONDecodeError:
            self.stdout.write(self.style.ERROR('💥 Failed to parse JSON from the website.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'💥 Unexpected error: {e}'))
    
    def load_posted_jobs(self, tracking_file):
        """Load the set of previously posted job slugs from the tracking file"""
        if tracking_file.exists():
            try:
                with open(tracking_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('posted_slugs', []))
            except (json.JSONDecodeError, IOError) as e:
                self.stdout.write(self.style.WARNING(f'⚠️ Could not read tracking file: {e}. Starting fresh.'))
                return set()
        return set()
    
    def save_posted_jobs(self, tracking_file, posted_jobs):
        """Save the updated set of posted job slugs to the tracking file"""
        try:
            # Keep only the last 500 slugs to prevent the file from growing indefinitely
            recent_slugs = list(posted_jobs)[-500:]
            
            with open(tracking_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'posted_slugs': recent_slugs,
                    'last_updated': str(__import__('datetime').datetime.now())
                }, f, indent=2, ensure_ascii=False)
            
            self.stdout.write(f'💾 Updated tracking file with {len(recent_slugs)} job slugs')
        except IOError as e:
            self.stdout.write(self.style.ERROR(f'❌ Could not save tracking file: {e}'))