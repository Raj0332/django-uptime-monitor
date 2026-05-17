"""URL patterns for the REST API."""
from django.urls import include, path
from rest_framework import routers
from rest_framework.authtoken.views import obtain_auth_token

from monitor.views import SiteViewSet

router = routers.DefaultRouter()
router.register(r"sites", SiteViewSet, basename="api-site")

urlpatterns = [
    path("", include(router.urls)),
    path("auth/token/", obtain_auth_token, name="api-token"),
]
