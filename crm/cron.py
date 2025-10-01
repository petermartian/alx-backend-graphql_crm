from datetime import datetime
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from requests.exceptions import RequestException

# This is the heartbeat function from Task 2
def log_crm_heartbeat():
    """
    Logs a heartbeat message to a file to confirm the CRM is alive.
    Optionally pings the GraphQL endpoint using the gql library.
    """
    log_file = "/tmp/crm_heartbeat_log.txt"
    timestamp = datetime.now().strftime("%d/%m/%Y-%H:%M:%S")
    message = f"{timestamp} CRM is alive"

    # Optional: Verify GraphQL endpoint is responsive using gql
    try:
        transport = RequestsHTTPTransport(url="http://localhost:8000/graphql", verify=True, retries=3)
        client = Client(transport=transport, fetch_schema_from_transport=False)
        query = gql('{ hello }')
        client.execute(query)
        message += " (GraphQL endpoint OK)"
    except RequestException:
        message += " (GraphQL endpoint is unreachable)"
    except Exception:
        message += " (GraphQL endpoint check failed)"

    # Append the message to the log file
    with open(log_file, "a") as f:
        f.write(message + "\n")

# This is the stock update function from Task 3
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
        transport = RequestsHTTPTransport(url="http://localhost:8000/graphql", verify=True, retries=3)
        client = Client(transport=transport, fetch_schema_from_transport=False)
        query = gql(mutation_query)
        data = client.execute(query)

        with open(log_file, "a") as f:
            f.write(f"--- Stock Update Log [{timestamp}] ---\n")
            result = data['updateLowStockProducts']
            f.write(f"Status: {result['message']}\n")
            if result.get('updatedProducts'):
                for product in result['updatedProducts']:
                    f.write(f"  - Restocked '{product['name']}' to new stock level: {product['stock']}\n")

    except Exception as e:
        with open(log_file, "a") as f:
            f.write(f"--- ERROR Log [{timestamp}] ---\n")
            f.write(f"Failed to execute GraphQL mutation: {e}\n")