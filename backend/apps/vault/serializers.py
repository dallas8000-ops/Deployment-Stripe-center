from rest_framework import serializers


class VaultEntrySerializer(serializers.Serializer):
    key = serializers.CharField()
    display = serializers.CharField()
    verified = serializers.BooleanField()
    verifiedAt = serializers.CharField(allow_null=True, required=False)
    verificationMessage = serializers.CharField(allow_null=True, required=False)
    mode = serializers.CharField()
    readable = serializers.BooleanField(required=False)


class VaultHealthSerializer(serializers.Serializer):
    masterKeyValid = serializers.BooleanField()
    unreadableCount = serializers.IntegerField()
    totalCount = serializers.IntegerField()


class VaultKeyListSerializer(serializers.Serializer):
    keys = serializers.ListField(child=serializers.CharField())
    entries = VaultEntrySerializer(many=True)
    initialized = serializers.BooleanField()
    vaultHealth = VaultHealthSerializer(required=False)


class VaultSetSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=128)
    value = serializers.CharField(write_only=True, allow_blank=False)

    def validate_key(self, value: str) -> str:
        key = value.strip()
        if not key:
            raise serializers.ValidationError("Key cannot be empty")
        return key


class VaultDeleteSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=128)
    confirm = serializers.BooleanField()

    def validate(self, attrs):
        if not attrs.get("confirm"):
            raise serializers.ValidationError({"confirm": "Confirmation required to delete a secret."})
        return attrs


class VaultImportSerializer(serializers.Serializer):
    env_file = serializers.CharField(max_length=256, default="auto", required=False)


class VaultImportAllSerializer(serializers.Serializer):
    legacy_passphrase = serializers.CharField(required=False, allow_blank=True, write_only=True)
    include_legacy = serializers.BooleanField(default=True, required=False)
    include_env = serializers.BooleanField(default=True, required=False)
