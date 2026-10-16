import os
import json
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from pathlib import Path
from dotenv import load_dotenv

class Command(BaseCommand):
    help = 'Scrapes FULL tender details from 2merkato.com (requires login) and posts to Telegram'

    def add_arguments(self, parser):
        parser.add_argument('--groups', nargs='+', type=str, required=True, help='Telegram Chat IDs')

    def handle(self, *args, **options):
        groups = options['groups']
        token = os.getenv('ETHIOGEN_BOT_TOKEN')
        if not token:
            self.stdout.write(self.style.ERROR('❌ ETHIOGEN_BOT_TOKEN environment variable is not set!'))
            return

        load_dotenv()
        email = os.getenv('MERKATO_EMAIL')
        password = os.getenv('MERKATO_PASSWORD')
        
        if not email or not password:
            self.stdout.write(self.style.ERROR('❌ MERKATO_EMAIL or MERKATO_PASSWORD not found in .env file!'))
            return

        url = 'https://tender.2merkato.com/tenders'
        tracking_file = Path(__file__).parent.parent.parent / 'posted_tenders.json'
        posted_tenders = self.load_posted(tracking_file)

        self.stdout.write(self.style.SUCCESS(f'🔄 Authenticating with 2merkato.com...'))
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        })
        
        try:
            session.get('https://tender.2merkato.com/login', timeout=10)
            login_payload = {'email': email, 'password': password}
            login_resp = session.post('https://tender.2merkato.com/login', data=login_payload, timeout=10)
            
            if 'logout' not in login_resp.text.lower() and login_resp.status_code != 200:
                self.stdout.write(self.style.ERROR('❌ Login failed. Check your MERKATO_EMAIL and MERKATO_PASSWORD in .env'))
                return
            
            self.stdout.write(self.style.SUCCESS('✅ Login successful! Fetching tenders...'))
            
            list_resp = session.get(url, timeout=15)
            list_soup = BeautifulSoup(list_resp.text, 'html.parser')
            app_div = list_soup.find('div', attrs={'data-page': True})
            
            if not app_div or 'data-page' not in app_div.attrs:
                self.stdout.write(self.style.ERROR('❌ Could not find Inertia data-page on tenders list.'))
                return
            
            page_data = json.loads(app_div['data-page'])
            tenders_list = page_data.get('props', {}).get('tenders', {}).get('data', [])
            
            self.stdout.write(f'📊 Found {len(tenders_list)} tenders in the list.')
            
            new_tenders = [t for t in tenders_list if str(t.get('id', '')) not in posted_tenders]
            new_tenders = new_tenders[:5]  # Increased to 5 to account for skipped ones
            
            self.stdout.write(f'🆕 Found {len(new_tenders)} NEW tenders to process.')
            
            if not new_tenders:
                self.stdout.write(self.style.SUCCESS('✅ No new tenders to post. All have been sent recently.'))
                return

            posted_count = 0
            for tender in new_tenders:
                tender_id = str(tender.get('id', ''))
                title = tender.get('title', 'Unknown Title')
                
                self.stdout.write(f'📥 Fetching full details for: {title[:50]}...')
                
                detail_url = f'https://tender.2merkato.com/tenders/{tender_id}'
                detail_resp = session.get(detail_url, timeout=15)
                detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
                detail_app = detail_soup.find('div', attrs={'data-page': True})
                
                if not detail_app or 'data-page' not in detail_app.attrs:
                    self.stdout.write(self.style.WARNING(f'⚠️ Skipping {tender_id}: Detail page data not found.'))
                    continue
                
                detail_data = json.loads(detail_app['data-page'])
                props = detail_data.get('props', {})
                full_tender = props.get('tender', {})
                
                # --- CRITICAL FIX: Skip if tender data is missing or empty ---
                if not full_tender or 'id' not in full_tender:
                    self.stdout.write(self.style.WARNING(f'⚠️ Skipping {tender_id}: Tender data is restricted, expired, or incomplete.'))
                    continue
                
                # --- CORRECTED DATA EXTRACTION ---
                company_data = full_tender.get('company', {})
                if isinstance(company_data, dict):
                    company_name = company_data.get('name_en') or company_data.get('name_am') or 'Unknown Company'
                else:
                    company_name = str(company_data) if company_data else 'Unknown Company'
                
                region_data = full_tender.get('region', {})
                if isinstance(region_data, dict):
                    region_name = region_data.get('name_en') or region_data.get('name_am') or 'Unknown Region'
                else:
                    region_name = str(region_data) if region_data else 'Unknown Region'
                
                closing_date = full_tender.get('bid_closing_date_text') or full_tender.get('bid_closing_date', 'N/A')
                if closing_date and closing_date != 'N/A' and ' ' in str(closing_date):
                    closing_date = str(closing_date).split(' ')[0]
                
                doc_price = full_tender.get('bid_document_price')
                doc_price_str = f"{doc_price} Birr" if doc_price else "Free / N/A"
                
                raw_desc = full_tender.get('description', '')
                clean_desc = BeautifulSoup(raw_desc, 'html.parser').get_text(separator='\n', strip=True) if raw_desc else 'No description provided.'
                clean_desc = (clean_desc[:1500] + '\n\n...(truncated)') if len(clean_desc) > 1500 else clean_desc
                
                raw_ai = full_tender.get('ai_summary', '')
                clean_ai = BeautifulSoup(raw_ai, 'html.parser').get_text(separator='\n', strip=True) if raw_ai else ''
                clean_ai = (clean_ai[:500] + '...') if len(clean_ai) > 500 else clean_ai

                # --- FORMAT TELEGRAM MESSAGE ---
                message = f"📢 *New Tender Announcement!*\n\n"
                message += f"📌 *Title:* {title}\n"
                message += f"🏢 *Company:* {company_name}\n"
                message += f"📍 *Region:* {region_name}\n"
                message += f"⏰ *Closing:* {closing_date}\n"
                message += f"💰 *Doc Price:* {doc_price_str}\n\n"
                
                if clean_ai:
                    message += f"🤖 *AI Summary:*\n{clean_ai}\n\n"
                    
                message += f"📝 *Description:*\n{clean_desc}\n\n"
                #message += f"🔗 *View & Apply:* {detail_url}"
                
                # --- SEND TO TELEGRAM ---
                for group_id in groups:
                    try:
                        send_url = f'https://api.telegram.org/bot{token}/sendMessage'
                        payload = {
                            'chat_id': group_id,
                            'text': message,
                            'parse_mode': 'Markdown',
                            'disable_web_page_preview': True
                        }
                        r = requests.post(send_url, json=payload, timeout=15)
                        result = r.json()
                        
                        if result.get('ok'):
                            self.stdout.write(self.style.SUCCESS(f'✅ Successfully posted to group {group_id}'))
                            posted_count += 1
                            posted_tenders.add(tender_id)
                        else:
                            self.stdout.write(self.style.ERROR(f'❌ Failed to post to {group_id}: {result.get("description")}'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'❌ Error sending to {group_id}: {str(e)}'))
            
            self.save_posted(tracking_file, posted_tenders)
            
            if posted_count > 0:
                self.stdout.write(self.style.SUCCESS(f'\n🎉 Done! Posted {posted_count} detailed tender(s).'))
            else:
                self.stdout.write(self.style.WARNING('\n⚠️ No valid tenders were posted (all were skipped or already posted).'))
                
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'💥 Network error: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'💥 Unexpected error: {e}'))

    def load_posted(self, file):
        if file.exists():
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def save_posted(self, file, data):
        try:
            recent_ids = list(data)[-500:]
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(recent_ids, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Could not save tracking file: {e}'))