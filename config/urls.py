"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", include("api.urls")),
    path("", include("accounts_core.urls")),
    path("catalog/", include("catalog.urls")),
    path("sales/", include("sales.urls")),
    path("purchases/", include("purchases.urls")),
    path("treasury/", include("treasury.urls")),
    path("expenses/", include("expenses.urls")),
    path("reporting/", include("reporting.urls")),
    # Legacy / mistyped paths → current routes
    path("accounts/clients/", RedirectView.as_view(url="/clients/", permanent=False)),
    path("accounts/suppliers/", RedirectView.as_view(url="/suppliers/", permanent=False)),
    path("catalog/service_types/", RedirectView.as_view(url="/catalog/service-types/", permanent=False)),
    path("service-types/", RedirectView.as_view(url="/catalog/service-types/", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
