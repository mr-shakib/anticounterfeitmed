"""Request shapes for the consumer API."""

from __future__ import annotations

from rest_framework import serializers

from medcrypto.tokens import TOKEN_TEXT_LENGTH


class PrepareSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=TOKEN_TEXT_LENGTH, max_length=TOKEN_TEXT_LENGTH)
    nonce = serializers.CharField(max_length=64)


class ConfirmSerializer(serializers.Serializer):
    unit_id = serializers.UUIDField()
    challenge_id = serializers.UUIDField()
    idempotency_key = serializers.CharField(max_length=80)
    nonce = serializers.CharField(max_length=64)


class OperationStatusSerializer(serializers.Serializer):
    nonce = serializers.CharField(max_length=64)


class PackageStatusSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=TOKEN_TEXT_LENGTH, max_length=TOKEN_TEXT_LENGTH)
    nonce = serializers.CharField(max_length=64)


class SessionCreateSerializer(serializers.Serializer):
    installation_id = serializers.CharField(max_length=64, required=False, allow_blank=True)


class ReportCreateSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=30)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    token = serializers.CharField(
        min_length=TOKEN_TEXT_LENGTH, max_length=TOKEN_TEXT_LENGTH,
        required=False, allow_blank=True,
    )
    external_reference = serializers.CharField(max_length=64, required=False, allow_blank=True)
    batch_number_text = serializers.CharField(max_length=100, required=False, allow_blank=True)
    pharmacy_note = serializers.CharField(max_length=300, required=False, allow_blank=True)
