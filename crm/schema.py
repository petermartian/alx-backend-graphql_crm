from graphql import GraphQLError
import decimal
import graphene
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from .models import Customer, Product, Order
from .filters import CustomerFilter, ProductFilter, OrderFilter

# =========================
# GraphQL Types
# =========================
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone", "created_at")
        filterset_class = CustomerFilter
        interfaces = (graphene.relay.Node,)

class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = ("id", "name", "price", "stock", "created_at")
        filterset_class = ProductFilter
        interfaces = (graphene.relay.Node,)

class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        fields = ("id", "customer", "products", "total_amount", "order_date")
        filterset_class = OrderFilter
        interfaces = (graphene.relay.Node,)

# =========================
# Helper Functions
# =========================
def flatten_validation_errors(validation_error):
    """Flattens Django validation errors into a readable string message."""
    return "; ".join([f"{k}: {', '.join(v)}" for k, v in validation_error.message_dict.items()])

# =========================
# Input Types for Filters
# =========================
class CustomerFilterInput(graphene.InputObjectType):
    name_icontains = graphene.String()
    email_icontains = graphene.String()
    created_at_gte = graphene.DateTime()
    created_at_lte = graphene.DateTime()
    phone_pattern = graphene.String()

class ProductFilterInput(graphene.InputObjectType):
    name_icontains = graphene.String()
    price_gte = graphene.Decimal()
    price_lte = graphene.Decimal()
    stock_gte = graphene.Int()
    stock_lte = graphene.Int()
    low_stock = graphene.Boolean()

class OrderFilterInput(graphene.InputObjectType):
    total_amount_gte = graphene.Decimal()
    total_amount_lte = graphene.Decimal()
    order_date_gte = graphene.DateTime()
    order_date_lte = graphene.DateTime()
    customer_name = graphene.String()
    product_name = graphene.String()
    product_id = graphene.ID()

# =========================
# Queries
# =========================
class Query(graphene.ObjectType):
    hello = graphene.String(default_value="Hello, GraphQL!")
    all_customers = DjangoFilterConnectionField(CustomerType, filterset_class=CustomerFilter, order_by=graphene.String())
    all_products = DjangoFilterConnectionField(ProductType, filterset_class=ProductFilter, order_by=graphene.String())
    all_orders = DjangoFilterConnectionField(OrderType, filterset_class=OrderFilter, order_by=graphene.String())

    def resolve_all_customers(self, info, **kwargs):
        queryset = Customer.objects.all()
        order_by = kwargs.get('order_by')
        if order_by:
            queryset = queryset.order_by(order_by)
        return queryset

    def resolve_all_products(self, info, **kwargs):
        queryset = Product.objects.all()
        order_by = kwargs.get('order_by')
        if order_by:
            queryset = queryset.order_by(order_by)
        return queryset

    def resolve_all_orders(self, info, **kwargs):
        queryset = Order.objects.select_related("customer").prefetch_related("products").all()
        order_by = kwargs.get('order_by')
        if order_by:
            queryset = queryset.order_by(order_by)
        return queryset

# =========================
# Mutations (Retained from Previous Schema)
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
# Root Mutation
# =========================
class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()

# =========================
# Root Schema
# =========================
schema = graphene.Schema(query=Query, mutation=Mutation)