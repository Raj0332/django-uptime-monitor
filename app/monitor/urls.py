"""URL patterns for the monitor app (HTML views under /sites/)."""
from django.urls import path

from monitor import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("add/", views.SiteCreateView.as_view(), name="site_create"),
    path("<int:pk>/", views.SiteDetailView.as_view(), name="site_detail"),
    path("<int:pk>/delete/", views.SiteDeleteView.as_view(), name="site_delete"),
    path("<int:pk>/toggle/", views.SiteToggleView.as_view(), name="site_toggle"),
    path("<int:pk>/card/", views.SiteCardView.as_view(), name="site_card"),
]
