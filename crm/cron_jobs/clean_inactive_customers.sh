#!/bin/bash

# This script must be run from the Django project's root directory.
# The crontab entry will handle changing to the correct directory and activating the virtual environment.

# The Python command to be executed by Django's shell
PYTHON_CMD="
from django.utils import timezone
from datetime import timedelta
from crm.models import Customer, Order

one_year_ago = timezone.now() - timedelta(days=365)

# Find IDs of customers who HAVE placed an order in the last year
recent_customer_ids = Order.objects.filter(order_date__gte=one_year_ago).values_list('customer_id', flat=True).distinct()

# Find customers whose IDs are NOT in the recent list
inactive_customers = Customer.objects.exclude(id__in=recent_customer_ids)

count = inactive_customers.count()
inactive_customers.delete()

print(f'{count} inactive customers deleted.')
"

# Execute the command using the project's manage.py
# Note: The crontab will specify the full path to python from the venv
DELETED_INFO=$(python manage.py shell -c "$PYTHON_CMD")

# Log the output with a timestamp
echo "$(date '+%Y-%m-%d %H:%M:%S'): $DELETED_INFO" >> /tmp/customer_cleanup_log.txt