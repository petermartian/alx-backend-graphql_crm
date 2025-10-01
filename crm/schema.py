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
from django.db.models import Sum, Count
import decimal

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
                except (ValidationError, GraphQLError) as e:
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
        if input.price <= 0:
            raise GraphQLError("Price must be greater than zero")
        if input.stock < 0:
            raise GraphQLError("Stock cannot be negative")

        product = Product(name=input.name, price=input.price, stock=input.stock)
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

        products = Product.objects.filter(pk__in=input.product_ids)
        if products.count() != len(input.product_ids):
            raise GraphQLError("One or more product IDs are invalid")

        total = products.aggregate(total_amount=Sum('price'))['total_amount'] or decimal.Decimal("0.00")

        with transaction.atomic():
            order = Order.objects.create(
                customer=customer,
                order_date=input.order_date or timezone.now(),
                total_amount=total
            )
            order.products.add(*products)

        return CreateOrder(order=order)

# This is the new mutation for updating low-stock products
class UpdateLowStockProducts(graphene.Mutation):
    """
    Finds products with stock < 10 and increases their stock by 10.
    """
    class Arguments:
        pass # No arguments needed

    # Output fields
    updated_products = graphene.List(ProductType)
    success = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @transaction.atomic
    def mutate(root, info):
        low_stock_products = Product.objects.filter(stock__lt=10)
        
        if not low_stock_products.exists():
            return UpdateLowStockProducts(updated_products=[], success=True, message="No low stock products found.")

        updated_list = []
        for product in low_stock_products:
            product.stock += 10  # Simulate restocking
            product.save()
            updated_list.append(product)

        return UpdateLowStockProducts(
            updated_products=updated_list,
            success=True,
            message=f"Successfully restocked {len(updated_list)} products."
        )

# =========================
# Root Mutation
# =========================
class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()
    # Add the new mutation field to the single, unified Mutation class
    update_low_stock_products = UpdateLowStockProducts.Field()

# =========================
# Root Schema
# =========================
schema = graphene.Schema(query=Query, mutation=Mutation)

# crm/schema.py
# ... import statements ...


# ... (Keep all your existing Type and Mutation classes) ...

# =========================
# Queries
# =========================
class Query(graphene.ObjectType):
    # --- Fields from your first Query class ---
    hello = graphene.String(default_value="Hello, GraphQL!")
    all_customers = DjangoFilterConnectionField(CustomerType, filterset_class=CustomerFilter)
    all_products = DjangoFilterConnectionField(ProductType, filterset_class=ProductFilter)
    all_orders = DjangoFilterConnectionField(OrderType, filterset_class=OrderFilter)

    # --- Fields from your second Query class (for the report) ---
    total_customer_count = graphene.Int()
    total_order_count = graphene.Int()
    total_revenue = graphene.Decimal()

    # --- Resolvers for all fields ---
    def resolve_all_customers(self, info, **kwargs):
        return Customer.objects.all()

    def resolve_all_products(self, info, **kwargs):
        return Product.objects.all()

    def resolve_all_orders(self, info, **kwargs):
        return Order.objects.select_related("customer").prefetch_related("products").all()

    def resolve_total_customer_count(self, info):
        return Customer.objects.count()

    def resolve_total_order_count(self, info):
        return Order.objects.count()

    def resolve_total_revenue(self, info):
        revenue = Order.objects.aggregate(total_revenue=Sum('total_amount'))['total_revenue']
        return revenue or decimal.Decimal('0.00')