"""Root URL configuration."""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from monitor import views as monitor_views

urlpatterns = [
    path("", RedirectView.as_view(url="/sites/", permanent=False)),
    path("admin/", admin.site.urls),
    # Health / observability
    path("healthz/", monitor_views.HealthzView.as_view(), name="healthz"),
    path("readyz/", monitor_views.ReadyzView.as_view(), name="readyz"),
    # Prometheus metrics (django-prometheus provides this)
    path("", include("django_prometheus.urls")),
    # Auth
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="monitor/login.html"),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path("accounts/signup/", monitor_views.SignupView.as_view(), name="signup"),
    # Main app
    path("sites/", include("monitor.urls")),
    # REST API
    path("api/", include("monitor.api_urls")),
]
