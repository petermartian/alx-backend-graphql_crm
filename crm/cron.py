from datetime import datetime
import requests

def log_crm_heartbeat():
    """
    Logs a heartbeat message to a file to confirm the CRM is alive.
    Optionally pings the GraphQL endpoint.
    """
    log_file = "/tmp/crm_heartbeat_log.txt"
    timestamp = datetime.now().strftime("%d/%m/%Y-%H:%M:%S")
    message = f"{timestamp} CRM is alive"

    # Optional: Verify GraphQL endpoint is responsive
    try:
        response = requests.post(
            "http://localhost:8000/graphql",
            json={'query': '{ hello }'},
            timeout=5 # Add a timeout
        )
        if response.status_code == 200 and 'data' in response.json():
            message += " (GraphQL endpoint OK)"
        else:
            message += f" (GraphQL endpoint check failed with status: {response.status_code})"
    except requests.exceptions.RequestException:
        message += " (GraphQL endpoint is unreachable)"

    # Append the message to the log file
    with open(log_file, "a") as f:
        f.write(message + "\n")


# crm/cron.py

from datetime import datetime
import requests

# ... (keep the log_crm_heartbeat function from Task 2)

def update_low_stock():
    """
    Executes the UpdateLowStockProducts GraphQL mutation and logs the result.
    """
    log_file = "/tmp/low_stock_updates_log.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mutation_query = """
    mutation {
      updateLowStockProducts {
        success
        message
        updatedProducts {
          name
          stock
        }
      }
    }
    """

    try:
        response = requests.post("http://localhost:8000/graphql", json={'query': mutation_query}, timeout=10)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        with open(log_file, "a") as f:
            f.write(f"--- Stock Update Log [{timestamp}] ---\n")
            if data.get('errors'):
                f.write(f"An error occurred: {data['errors']}\n")
                return

            result = data['data']['updateLowStockProducts']
            f.write(f"Status: {result['message']}\n")
            if result['updatedProducts']:
                for product in result['updatedProducts']:
                    f.write(f"  - Restocked '{product['name']}' to new stock level: {product['stock']}\n")

    except requests.exceptions.RequestException as e:
        with open(log_file, "a") as f:
            f.write(f"--- ERROR Log [{timestamp}] ---\n")
            f.write(f"Failed to execute GraphQL mutation: {e}\n")