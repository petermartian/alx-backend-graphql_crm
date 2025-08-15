from graphql import GraphQLError
import decimal
import graphene
from graphene_django import DjangoObjectType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage
from django.db.models import Sum

from crm.models import Customer, Product, Order

# =========================
# Helper Functions
# =========================
def flatten_validation_errors(validation_error):
    """Flattens Django validation errors into a readable string message."""
    return "; ".join([f"{k}: {', '.join(v)}" for k, v in validation_error.message_dict.items()])

# =========================
# GraphQL Types
# =========================
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

# =========================
# Queries
# =========================
class Query(graphene.ObjectType):
    hello = graphene.String(default_value="Hello, GraphQL!")
    customers = graphene.List(CustomerType, page=graphene.Int(default_value=1), page_size=graphene.Int(default_value=10))
    products = graphene.List(ProductType, first=graphene.Int(), skip=graphene.Int())
    orders = graphene.List(OrderType, page=graphene.Int(default_value=1), page_size=graphene.Int(default_value=10))

    def resolve_customers(self, info, page, page_size):
        customers = Customer.objects.all()
        paginator = Paginator(customers, page_size)
        try:
            return paginator.page(page).object_list
        except EmptyPage:
            return []

    def resolve_products(self, info, first=None, skip=None):
        query = Product.objects.all()
        if skip is not None and skip < 0:
            raise GraphQLError("Skip cannot be negative")
        if first is not None and first <= 0:
            raise GraphQLError("First must be a positive integer")
        if skip:
            query = query[skip:]
        if first:
            query = query[:first]
        return query

    def resolve_orders(self, info, page, page_size):
        orders = Order.objects.select_related("customer").prefetch_related("products").all()
        paginator = Paginator(orders, page_size)
        try:
            return paginator.page(page).object_list
        except EmptyPage:
            return []

# =========================
# Mutations
# =========================
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
    def mutate(root, info, input):
        if Customer.objects.filter(email__iexact=input.email).exists():
            raise GraphQLError(f"Email already exists: {input.email}")
        
        customer = Customer(
            name=input.name,
            email=input.email,
            phone=input.phone or "",
        )
        try:
            customer.full_clean()
            customer.save()
            return CreateCustomerPayload(customer=customer, message="Customer created successfully")
        except ValidationError as e:
            raise GraphQLError(flatten_validation_errors(e))

class BulkCreateCustomers(graphene.Mutation):
    class Arguments:
        input = graphene.List(CreateCustomerInput, required=True)

    customers = graphene.List(CustomerType)
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input):
        created, errors = [], []

        for idx, payload in enumerate(input):
            with transaction.atomic():
                sid = transaction.savepoint()
                try:
                    if Customer.objects.filter(email__iexact=payload.email).exists():
                        raise GraphQLError(f"[{idx}] Email already exists: {payload.email}")

                    cust = Customer(
                        name=payload.name,
                        email=payload.email,
                        phone=payload.phone or "",
                    )
                    cust.full_clean()
                    cust.save()
                    created.append(cust)
                except ValidationError as e:
                    transaction.savepoint_rollback(sid)
                    errors.append(f"[{idx}] {flatten_validation_errors(e)}")
                except GraphQLError as e:
                    transaction.savepoint_rollback(sid)
                    errors.append(f"[{idx}] {str(e)}")
                except Exception as e:
                    transaction.savepoint_rollback(sid)
                    errors.append(f"[{idx}] Unexpected error: {str(e)}")

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
    def mutate(root, info, input):
        try:
            price = decimal.Decimal(str(input.price))
        except (ValueError, TypeError):
            raise GraphQLError("Price must be a valid decimal number")

        if price <= 0:
            raise GraphQLError("Price must be greater than zero")
        if input.stock < 0:
            raise GraphQLError("Stock cannot be negative")

        product = Product(name=input.name, price=price, stock=input.stock)
        try:
            product.full_clean()
            product.save()
            return CreateProduct(product=product)
        except ValidationError as e:
            raise GraphQLError(flatten_validation_errors(e))

class CreateOrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True)
    product_ids = graphene.List(graphene.ID, required=True)
    order_date = graphene.DateTime(required=False)

class CreateOrder(graphene.Mutation):
    class Arguments:
        input = CreateOrderInput(required=True)

    order = graphene.Field(OrderType)

    @staticmethod
    def mutate(root, info, input):
        try:
            customer = Customer.objects.get(pk=input.customer_id)
        except Customer.DoesNotExist:
            raise GraphQLError("Invalid customer ID")

        if not input.product_ids:
            raise GraphQLError("At least one product must be selected")

        id_list = list(set(int(i) for i in input.product_ids))
        products = Product.objects.filter(pk__in=id_list)
        if products.count() != len(id_list):
            raise GraphQLError("One or more product IDs are invalid")

        total = products.aggregate(total_amount=Sum('price'))['total_amount'] or decimal.Decimal("0.00")

        with transaction.atomic():
            order = Order.objects.create(
                customer=customer,
                order_date=input.order_date or timezone.now(),
                total_amount=total.quantize(decimal.Decimal("0.01"))
            )
            order.products.add(*products)

        return CreateOrder(order=order)

# =========================
# Root Schema
# =========================
class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)