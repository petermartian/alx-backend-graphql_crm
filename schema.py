import graphene
from graphene_django import DjangoObjectType
from crm.models import Customer  # Adjust based on your models

# Define a GraphQL type for your model
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        fields = "__all__"  # Or specify fields explicitly, e.g., ["name", "email"]

# Define the Query class
class Query(graphene.ObjectType):
    all_customers = graphene.List(CustomerType)
    customer_by_id = graphene.Field(CustomerType, id=graphene.Int(required=True))

    def resolve_all_customers(self, info):
        return Customer.objects.all()

    def resolve_customer_by_id(self, info, id):
        try:
            return Customer.objects.get(id=id)
        except Customer.DoesNotExist:
            return None

# Define the schema
schema = graphene.Schema(query=Query)