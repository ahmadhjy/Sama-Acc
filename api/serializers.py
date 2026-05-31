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
        if inst and inst.status != SalesInvoice.Status.DRAFT:
            if "grand_total" in attrs and attrs["grand_total"] != inst.grand_total:
                raise serializers.ValidationError(
                    {
                        "grand_total": "Cannot change total selling price after the invoice is posted or voided."
                    }
                )
            if "currency" in attrs and attrs.get("currency") != inst.currency:
                raise serializers.ValidationError(
                    {"currency": "Cannot change invoice currency after the invoice is posted or voided."}
                )
            if "exchange_rate_to_usd" in attrs:
                new_r = attrs.get("exchange_rate_to_usd")
                old_r = inst.exchange_rate_to_usd
                if new_r != old_r and not (new_r is None and old_r is None):
                    raise serializers.ValidationError(
                        {"exchange_rate_to_usd": "Cannot change the exchange rate after the invoice is posted or voided."}
                    )
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
