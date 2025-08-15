#!/usr/bin/env python3
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alx_backend_graphql_crm.settings")
django.setup()

from crm.models import Customer, Product

def run():
    # Customers
    c_data = [
        {"name": "Alice", "email": "alice@example.com", "phone": "+1234567890"},
        {"name": "Bob", "email": "bob@example.com", "phone": "123-456-7890"},
        {"name": "Carol", "email": "carol@example.com", "phone": ""},
    ]
    for d in c_data:
        Customer.objects.get_or_create(email=d["email"], defaults=d)

    # Products
    p_data = [
        {"name": "Laptop", "price": 999.99, "stock": 10},
        {"name": "Mouse", "price": 25.50, "stock": 100},
        {"name": "Keyboard", "price": 75.00, "stock": 40},
    ]
    for d in p_data:
        Product.objects.get_or_create(name=d["name"], defaults=d)

    print("Seeding complete.")

if __name__ == "__main__":
    run()
