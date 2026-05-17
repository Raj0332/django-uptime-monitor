from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from monitor.models import Site


class SignupForm(UserCreationForm):
    """User registration form with email field."""

    email = forms.EmailField(required=True, help_text="Required. Enter a valid email address.")

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]


class SiteForm(forms.ModelForm):
    """Form for creating and updating monitored sites."""

    class Meta:
        model = Site
        fields = ["name", "url", "check_interval_seconds", "timeout_seconds", "expected_status_code"]
        help_texts = {
            "name": "A friendly name for this site.",
            "url": "The full URL to monitor, including https://",
            "check_interval_seconds": "How often to check this site (minimum 30 seconds).",
            "timeout_seconds": "Request timeout in seconds (1–60).",
            "expected_status_code": "The HTTP status code that means the site is UP (usually 200).",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "w-full rounded border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"}),
            "url": forms.URLInput(attrs={"class": "w-full rounded border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500", "placeholder": "https://example.com"}),
            "check_interval_seconds": forms.NumberInput(attrs={"class": "w-full rounded border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"}),
            "timeout_seconds": forms.NumberInput(attrs={"class": "w-full rounded border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"}),
            "expected_status_code": forms.NumberInput(attrs={"class": "w-full rounded border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"}),
        }
