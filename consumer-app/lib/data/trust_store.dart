/// The keys this installation is willing to trust.
///
/// The app ships with an offline root public key. Everything else arrives in a
/// root-signed, versioned manifest, so a substituted key is refused even if an
/// attacker controls the connection.
///
/// Two rules matter here: the manifest version never goes backwards, and a key
/// marked revoked is refused rather than quietly accepted for old credentials.
library;

import 'dart:convert';
import 'dart:typed_data';

import '../crypto/verifier.dart';

class TrustedKey {
  final String keyId;
  final String purpose;
  final String? organizationId;
  final Uint8List publicKey;
  final String state;

  const TrustedKey({
    required this.keyId,
    required this.purpose,
    required this.organizationId,
    required this.publicKey,
    required this.state,
  });

  bool get isUsable => state == 'ACTIVE' || state == 'RETIRED';
  bool get isRevoked => state == 'REVOKED';
}

class TrustManifest {
  final int version;
  final DateTime issuedAt;
  final Map<String, TrustedKey> keys;

  const TrustManifest({
    required this.version,
    required this.issuedAt,
    required this.keys,
  });

  TrustedKey? operator [](String keyId) => keys[keyId];
}

class ManifestRejected implements Exception {
  final String reason;
  ManifestRejected(this.reason);
  @override
  String toString() => 'ManifestRejected: $reason';
}

/// Verifies a manifest against the offline root key and returns it.
///
/// [minimumVersion] is the highest version this installation has already seen.
/// Anything at or below it is refused as a rollback.
TrustManifest verifyManifest({
  required Uint8List rootPublicKey,
  required Uint8List payload,
  required Uint8List signature,
  required int minimumVersion,
}) {
  final ok = verifySignature(
    publicKey: rootPublicKey,
    payload: payload,
    signature: signature,
    context: SigContext.trustManifest,
  );
  if (!ok) throw ManifestRejected('root signature did not verify');

  final record = parseStrict(payload);
  if (record['schema'] != 'medicine-trust-manifest-v1') {
    throw ManifestRejected('unexpected manifest schema');
  }

  final version = record['version'];
  if (version is! int) throw ManifestRejected('manifest has no version');
  if (version <= minimumVersion) {
    // Refusing equality too would block a legitimate refresh, so only a
    // strictly older manifest is a rollback.
    if (version < minimumVersion) {
      throw ManifestRejected('manifest is older than one already accepted');
    }
  }

  final entries = record['keys'];
  if (entries is! List) throw ManifestRejected('manifest has no keys');

  final keys = <String, TrustedKey>{};
  for (final entry in entries) {
    if (entry is! Map) continue;
    final keyId = entry['key_id'] as String?;
    final hex = entry['public_key'] as String?;
    if (keyId == null || hex == null) continue;
    keys[keyId] = TrustedKey(
      keyId: keyId,
      purpose: entry['purpose'] as String? ?? '',
      organizationId: entry['organization_id'] as String?,
      publicKey: _fromHex(hex),
      state: entry['state'] as String? ?? 'ACTIVE',
    );
  }

  return TrustManifest(
    version: version,
    issuedAt: DateTime.tryParse(record['issued_at'] as String? ?? '') ?? DateTime.now(),
    keys: keys,
  );
}

Uint8List _fromHex(String hex) {
  final bytes = Uint8List(hex.length ~/ 2);
  for (var i = 0; i < bytes.length; i++) {
    bytes[i] = int.parse(hex.substring(i * 2, i * 2 + 2), radix: 16);
  }
  return bytes;
}

/// Base64 helper kept here so callers do not re-import dart:convert everywhere.
Uint8List decodeBase64(String value) => base64.decode(value);
