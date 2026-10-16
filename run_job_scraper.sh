#!/bin/bash
# Change to project directory
cd /home/syorelig/ethiogen/job_portal

# Activate the virtual environment
source /home/syorelig/virtualenv/ethiogen/3.13/bin/activate

# Set the bot token
export ETHIOGEN_BOT_TOKEN="YOUR_ACTUAL_BOT_TOKEN_HERE"

# Run the scraper and log the output
python manage.py post_website_update --url "https://ethiojobs.net/jobs/" --groups "-1003795541703" >> cron_job_scraper.log 2>&1