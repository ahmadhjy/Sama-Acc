from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts_core.models import Client, Supplier
from purchases.models import SupplierBill
from sales.models import SalesInvoice
from treasury.models import APAllocation, ARAllocation, Payment

from .serializers import (
    APAllocationSerializer,
    ARAllocationSerializer,
    ClientSerializer,
    PaymentSerializer,
    SalesInvoiceSerializer,
    SupplierBillSerializer,
    SupplierSerializer,
)


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all().order_by("name_en")
    serializer_class = ClientSerializer


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all().order_by("name")
    serializer_class = SupplierSerializer


class SalesInvoiceViewSet(viewsets.ModelViewSet):
    queryset = SalesInvoice.objects.all().order_by("-created_at")
    serializer_class = SalesInvoiceSerializer

    @action(detail=True, methods=["post"])
    def post_doc(self, request, pk=None):
        invoice = self.get_object()
        try:
            invoice.post(request.user)
            return Response({"status": "posted", "invoice_no": invoice.invoice_no})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def void_doc(self, request, pk=None):
        invoice = self.get_object()
        reason = request.data.get("reason", "API void")
        try:
            invoice.void(request.user, reason)
            return Response({"status": "voided"})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class SupplierBillViewSet(viewsets.ModelViewSet):
    queryset = SupplierBill.objects.all().order_by("-created_at")
    serializer_class = SupplierBillSerializer

    @action(detail=True, methods=["post"])
    def post_doc(self, request, pk=None):
        bill = self.get_object()
        try:
            bill.post(request.user)
            return Response({"status": "posted", "bill_no": bill.bill_no})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().order_by("-created_at")
    serializer_class = PaymentSerializer

    @action(detail=True, methods=["post"])
    def post_doc(self, request, pk=None):
        payment = self.get_object()
        try:
            payment.post(request.user)
            return Response({"status": "posted", "receipt_no": payment.receipt_no})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def void_doc(self, request, pk=None):
        payment = self.get_object()
        reason = request.data.get("reason", "API void")
        try:
            payment.void(reason)
            return Response({"status": "voided"})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class ARAllocationViewSet(viewsets.ModelViewSet):
    queryset = ARAllocation.objects.all().order_by("-created_at")
    serializer_class = ARAllocationSerializer


class APAllocationViewSet(viewsets.ModelViewSet):
    queryset = APAllocation.objects.all().order_by("-created_at")
    serializer_class = APAllocationSerializer
