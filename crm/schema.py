import decimal
import graphene
from graphene import relay
from graphene_django import DjangoObjectType
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum

from .models import Customer, Product, Order

# --------------------
# GraphQL Types
# --------------------
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone")

class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = ("id", "name", "price", "stock")

class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        fields = ("id", "customer", "products", "total_amount", "order_date")

# --------------------
# Query (you can extend later)
# --------------------
class Query(graphene.ObjectType):
    hello = graphene.String(default_value="Hello, GraphQL!")
    customers = graphene.List(CustomerType)
    products = graphene.List(ProductType)
    orders = graphene.List(OrderType)

    def resolve_customers(root, info):
        return Customer.objects.all()

    def resolve_products(root, info):
        return Product.objects.all()

    def resolve_orders(root, info):
        return Order.objects.select_related("customer").prefetch_related("products").all()

# --------------------
# Mutations
# --------------------
class CreateCustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)

class CreateCustomerPayload(graphene.ObjectType):
    customer = graphene.Field(CustomerType)
    message = graphene.String()

class CreateCustomer(graphene.Mutation):
    class Arguments:
        input = CreateCustomerInput(required=True)

    Output = CreateCustomerPayload

    @staticmethod
    def mutate(root, info, input: CreateCustomerInput):
        # Email uniqueness
        if Customer.objects.filter(email=input.email).exists():
            raise graphene.GraphQLError("Email already exists")

        customer = Customer(name=input.name, email=input.email, phone=input.phone or "")
        # Run model-level validators (phone format)
        try:
            customer.full_clean()
        except ValidationError as e:
            raise graphene.GraphQLError("; ".join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]))

        customer.save()
        return CreateCustomerPayload(customer=customer, message="Customer created successfully")


class BulkCreateCustomers(graphene.Mutation):
    class Arguments:
        input = graphene.List(CreateCustomerInput, required=True)

    customers = graphene.List(CustomerType)
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input):
        created = []
        errors = []

        # Partial success with savepoints per record
        for idx, payload in enumerate(input):
            with transaction.atomic():
                sid = transaction.savepoint()
                try:
                    if Customer.objects.filter(email=payload.email).exists():
                        raise graphene.GraphQLError(f"[{idx}] Email already exists: {payload.email}")
                    cust = Customer(name=payload.name, email=payload.email, phone=payload.phone or "")
                    cust.full_clean()
                    cust.save()
                    created.append(cust)
                    transaction.savepoint_commit(sid)
                except (ValidationError, graphene.GraphQLError) as e:
                    transaction.savepoint_rollback(sid)
                    if isinstance(e, ValidationError):
                        msg = "; ".join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
                        errors.append(f"[{idx}] {msg}")
                    else:
                        errors.append(str(e))
                except Exception as e:
                    transaction.savepoint_rollback(sid)
                    errors.append(f"[{idx}] Unexpected error: {e}")

        return BulkCreateCustomers(customers=created, errors=errors)


class CreateProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    price = graphene.Decimal(required=True)
    stock = graphene.Int(required=False, default_value=0)

class CreateProduct(graphene.Mutation):
    class Arguments:
        input = CreateProductInput(required=True)

    product = graphene.Field(ProductType)

    @staticmethod
    def mutate(root, info, input: CreateProductInput):
        # Validate positive price and non-negative stock
        try:
            price = decimal.Decimal(input.price)
        except Exception:
            raise graphene.GraphQLError("Invalid price")

        if price <= 0:
            raise graphene.GraphQLError("Price must be positive")

        stock = input.stock or 0
        if stock < 0:
            raise graphene.GraphQLError("Stock cannot be negative")

        product = Product(name=input.name, price=price, stock=stock)
        product.full_clean()
        product.save()
        return CreateProduct(product=product)


class CreateOrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True)
    product_ids = graphene.List(graphene.ID, required=True)
    order_date = graphene.DateTime(required=False)

class CreateOrder(graphene.Mutation):
    class Arguments:
        input = CreateOrderInput(required=True)

    order = graphene.Field(OrderType)

    @staticmethod
    def mutate(root, info, input: CreateOrderInput):
        # Validate customer
        try:
            customer = Customer.objects.get(pk=input.customer_id)
        except Customer.DoesNotExist:
            raise graphene.GraphQLError("Invalid customer ID")

        # Validate products
        if not input.product_ids:
            raise graphene.GraphQLError("At least one product must be selected")

        products = list(Product.objects.filter(pk__in=input.product_ids))
        if len(products) != len(set(map(int, input.product_ids))):
            raise graphene.GraphQLError("One or more product IDs are invalid")

        # Create order in a transaction
        with transaction.atomic():
            order = Order.objects.create(
                customer=customer,
                order_date=input.order_date or timezone.now()
            )
            order.products.add(*products)

            # Ensure accurate total by summing current product prices
            total = sum((p.price for p in products), decimal.Decimal("0.00"))
            order.total_amount = total.quantize(decimal.Decimal("0.01"))
            order.save()

        return CreateOrder(order=order)

# --------------------
# Root Mutation
# --------------------
class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()
