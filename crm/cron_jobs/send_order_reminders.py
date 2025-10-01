#!/usr/bin/env python

import os
import sys
from datetime import datetime, timedelta
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

# Add the project root to the Python path
# This allows the script to be run from anywhere and still find the crm app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def send_reminders():
    """
    Queries the GraphQL endpoint for recent orders and logs reminders.
    """
    transport = RequestsHTTPTransport(url="http://localhost:8000/graphql", verify=True, retries=3)
    client = Client(transport=transport, fetch_schema_from_transport=False)

    # Define the GraphQL query with a variable for the date
    query = gql("""
        query GetRecentOrders($dateLimit: DateTime!) {
            orders(orderDate_Gte: $dateLimit) {
                id
                customer {
                    email
                }
            }
        }
    """)

    # Calculate the date 7 days ago
    date_limit = datetime.now() - timedelta(days=7)
    params = {"dateLimit": date_limit.isoformat()}

    log_file = "/tmp/order_reminders_log.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Execute the query
        result = client.execute(query, variable_values=params)

        with open(log_file, "a") as f:
            f.write(f"--- Reminder Log [{timestamp}] ---\n")
            if result and 'orders' in result and result['orders']:
                for order in result['orders']:
                    # Assuming order['id'] is a base64 encoded string like 'T3JkZXJOb2RlOjE='
                    # You might need to decode it or adjust based on your actual ID format
                    log_line = f"Reminder for Order ID: {order['id']}, Customer: {order['customer']['email']}\n"
                    f.write(log_line)
            else:
                f.write("No recent orders found to process.\n")

    except Exception as e:
        with open(log_file, "a") as f:
            f.write(f"--- ERROR Log [{timestamp}] ---\n")
            f.write(f"An error occurred: {e}\n")

    print("Order reminders processed!")

if __name__ == "__main__":
    send_reminders()