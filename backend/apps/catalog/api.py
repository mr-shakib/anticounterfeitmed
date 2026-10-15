"""Product and batch endpoints.

Every queryset is filtered by the caller's own organization. A manufacturer
never names the organization it is acting for -- that comes from the
authenticated membership -- so there is no field to tamper with.
"""

from __future__ import annotations

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from apps.audit.models import AuditAction, AuditEvent
from apps.catalog.models import (
    PRODUCT_INFORMATION_FIELDS,
    PRODUCT_INFORMATION_MAX_BYTES,
    PRODUCT_INFORMATION_MAX_CHARS,
    Batch,
    Product,
)
from apps.organizations.permissions import STAFF_AUTH, IsManufacturerStaff, owns
from apps.qc.services import batches_progress


def clean_information(value) -> dict[str, str]:
    """Known sections only, trimmed, empty ones dropped, within the size limits."""
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise serializers.ValidationError("Expected sections keyed by name.")
    unknown = sorted(set(value) - set(PRODUCT_INFORMATION_FIELDS))
    if unknown:
        raise serializers.ValidationError(f"Unknown sections: {', '.join(unknown)}.")
    cleaned: dict[str, str] = {}
    for field in PRODUCT_INFORMATION_FIELDS:
        text = value.get(field)
        if text is None:
            continue
        if not isinstance(text, str):
            raise serializers.ValidationError(f"{field} must be text.")
        text = text.strip()
        if len(text) > PRODUCT_INFORMATION_MAX_CHARS:
            raise serializers.ValidationError(
                f"{field} is longer than {PRODUCT_INFORMATION_MAX_CHARS} characters."
            )
        if text:
            cleaned[field] = text
    if sum(len(t.encode("utf-8")) for t in cleaned.values()) > PRODUCT_INFORMATION_MAX_BYTES:
        raise serializers.ValidationError(
            "The information is too long in total. Shorten the longest sections."
        )
    return cleaned


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id", "brand", "generic", "strength", "dosage_form",
            "pack_description", "registration_reference", "information",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_information(self, value):
        return clean_information(value)


class InformationSerializer(serializers.Serializer):
    information = serializers.JSONField()

    def validate_information(self, value):
        return clean_information(value)


class BatchSerializer(serializers.ModelSerializer):
    product_brand = serializers.CharField(source="product.brand", read_only=True)

    class Meta:
        model = Batch
        fields = [
            "id", "product", "product_brand", "batch_number", "manufactured_on",
            "expires_on", "planned_unit_count", "is_recalled", "recalled_at",
            "recall_notice", "created_at",
        ]
        read_only_fields = ["id", "is_recalled", "recalled_at", "recall_notice", "created_at"]

    def validate(self, attrs):
        # Expiry is never inferred. If a label carries only month and year, the
        # manufacturer supplies the intended final valid date.
        manufactured = attrs.get("manufactured_on")
        expires = attrs.get("expires_on")
        if manufactured and expires and expires <= manufactured:
            raise serializers.ValidationError(
                {"expires_on": "Expiry must be after the manufacturing date."}
            )
        return attrs


@api_view(["GET", "POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def products(request):
    org = request.membership.organization
    if request.method == "GET":
        queryset = Product.objects.filter(manufacturer=org).order_by("brand")
        return Response(ProductSerializer(queryset, many=True).data)

    serializer = ProductSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    product = serializer.save(manufacturer=org)
    return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def product_information(request, product_id):
    """Replace a product's optional information. Nothing else about it can change.

    The fields frozen into credentials -- brand, strength and the rest -- are
    not editable here or anywhere. This text is shown at check time from the
    signed status statement, so an edit reaches the app at once; it is
    recorded, because it is what a patient reads.
    """
    product = Product.objects.select_related("manufacturer").filter(pk=product_id).first()
    if product is None or not owns(request.membership, product.manufacturer):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such product."},
            status=status.HTTP_404_NOT_FOUND,
        )
    serializer = InformationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    information = serializer.validated_data["information"]

    with transaction.atomic():
        before = sorted(product.information or {})
        product.information = information
        product.save(update_fields=["information", "updated_at"])
        AuditEvent.objects.create(
            action=AuditAction.PRODUCT_INFORMATION_UPDATED,
            organization=product.manufacturer,
            actor_user=request.user,
            reason=f"Information for {product.brand} updated",
            detail={
                "product_id": str(product.id),
                "sections_before": before,
                "sections_after": sorted(information),
            },
        )
    return Response(ProductSerializer(product).data)


@api_view(["GET", "POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def batches(request):
    org = request.membership.organization
    if request.method == "GET":
        rows = list(
            Batch.objects.filter(product__manufacturer=org)
            .select_related("product")
            .order_by("-created_at")
        )
        progress = batches_progress([b.id for b in rows])
        return Response(
            [
                {**BatchSerializer(b).data, "progress": progress[b.id]}
                for b in rows
            ]
        )

    serializer = BatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    # The product must belong to the caller; otherwise a batch could be hung
    # off another manufacturer's catalogue entry.
    product = serializer.validated_data["product"]
    if not owns(request.membership, product.manufacturer):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such product."},
            status=status.HTTP_404_NOT_FOUND,
        )

    batch = serializer.save()
    return Response(BatchSerializer(batch).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def batch_detail(request, batch_id):
    batch = (
        Batch.objects.select_related("product__manufacturer").filter(pk=batch_id).first()
    )
    if batch is None or not owns(request.membership, batch.product.manufacturer):
        # Indistinguishable from a batch that does not exist: a 403 would
        # confirm that another manufacturer's batch id is real.
        return Response(
            {"code": "NOT_FOUND", "detail": "No such batch."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(BatchSerializer(batch).data)
