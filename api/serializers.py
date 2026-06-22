from rest_framework import serializers

from accounts_core.models import Client, Supplier
from purchases.models import SupplierBill
from sales.models import SalesInvoice
from treasury.models import APAllocation, ARAllocation, Payment


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = "__all__"


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = "__all__"


class SalesInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesInvoice
        fields = "__all__"
        read_only_fields = [
            "subtotal",
            "discount_total",
            "grand_total",
            "subtotal_usd",
            "discount_total_usd",
            "grand_total_usd",
            "posted_at",
            "posted_by",
            "voided_at",
            "voided_by",
        ]

    def validate(self, attrs):
        inst = self.instance
        if inst and inst.status == SalesInvoice.Status.VOIDED:
            raise serializers.ValidationError("Voided invoices cannot be changed.")
        return attrs


class SupplierBillSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierBill
        fields = "__all__"
        read_only_fields = ["subtotal", "grand_total", "posted_at", "posted_by"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = ["posted_at", "posted_by", "voided_at", "void_reason"]


class ARAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ARAllocation
        fields = "__all__"


class APAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = APAllocation
        fields = "__all__"
