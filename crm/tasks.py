import requests 
from celery import shared_task
from datetime import datetime
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

@shared_task
def generate_crm_report():
    """
    A Celery task that queries the GraphQL endpoint to generate a CRM summary report.
    """
    log_file = "/tmp/crm_report_log.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # The GraphQL query to fetch aggregated data
    query = gql("""
        query CrmReportQuery {
            totalCustomerCount
            totalOrderCount
            totalRevenue
        }
    """)

    try:
        transport = RequestsHTTPTransport(url="http://localhost:8000/graphql", verify=True, retries=3)
        client = Client(transport=transport, fetch_schema_from_transport=False)
        result = client.execute(query)

        customers = result.get('totalCustomerCount', 0)
        orders = result.get('totalOrderCount', 0)
        revenue = result.get('totalRevenue', 0.0)

        report_line = (
            f"{timestamp} - Report: {customers} customers, {orders} orders, ${revenue:.2f} revenue.\n"
        )

        with open(log_file, "a") as f:
            f.write(report_line)

        return f"Report generated successfully: {customers} customers, {orders} orders."

    except Exception as e:
        error_message = f"{timestamp} - ERROR: Failed to generate CRM report. Reason: {e}\n"
        with open(log_file, "a") as f:
            f.write(error_message)
        return f"Failed to generate report: {e}"