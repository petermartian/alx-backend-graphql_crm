# settings.py

# Django-crontab configuration
CRONJOBS = [
    # Runs the heartbeat log every 5 minutes
    ('*/5 * * * *', 'crm.cron.log_crm_heartbeat'),
    # Runs the low stock update every 12 hours
    ('0 */12 * * *', 'crm.cron.update_low_stock'),
]