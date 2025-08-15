from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView
from graphene_django.views import GraphQLView

urlpatterns = [
    path("", RedirectView.as_view(url="/graphql/", permanent=False)),
    path("admin/", admin.site.urls),
    path("graphql/", csrf_exempt(GraphQLView.as_view(graphiql=True))),
]
