from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    APAllocationViewSet,
    ARAllocationViewSet,
    ClientViewSet,
    PaymentViewSet,
    SalesInvoiceViewSet,
    SupplierBillViewSet,
    SupplierViewSet,
)

router = DefaultRouter()
router.register("clients", ClientViewSet, basename="api-clients")
router.register("suppliers", SupplierViewSet, basename="api-suppliers")
router.register("sales/invoices", SalesInvoiceViewSet, basename="api-sales-invoices")
router.register("purchases/bills", SupplierBillViewSet, basename="api-purchases-bills")
router.register("treasury/payments", PaymentViewSet, basename="api-treasury-payments")
router.register("allocations/ar", ARAllocationViewSet, basename="api-allocations-ar")
router.register("allocations/ap", APAllocationViewSet, basename="api-allocations-ap")

urlpatterns = [
    path("", include(router.urls)),
]
