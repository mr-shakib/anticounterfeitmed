"""Product and batch endpoints.

Every queryset is filtered by the caller's own organization. A manufacturer
never names the organization it is acting for -- that comes from the
authenticated membership -- so there is no field to tamper with.
"""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from apps.catalog.models import Batch, Product
from apps.organizations.permissions import STAFF_AUTH, IsManufacturerStaff, owns


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id", "brand", "generic", "strength", "dosage_form",
            "pack_description", "registration_reference", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


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


@api_view(["GET", "POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def batches(request):
    org = request.membership.organization
    if request.method == "GET":
        queryset = (
            Batch.objects.filter(product__manufacturer=org)
            .select_related("product")
            .order_by("-created_at")
        )
        return Response(BatchSerializer(queryset, many=True).data)

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
