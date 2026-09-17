/// Storage for this installation's session credential and its receipts.
///
/// The credential goes in the platform keystore. Receipts are ordinary local
/// storage: they contain no token and nothing about anyone else, and they are
/// historical evidence rather than current truth.
library;

import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _credentialKey = 'consumer_session_credential';
const _receiptsKey = 'verification_receipts';
const _manifestVersionKey = 'trust_manifest_version';

class Receipt {
  final String unitId;
  final String outcome;
  final String brand;
  final String batchNumber;
  final DateTime checkedAt;
  final bool firstVerification;

  const Receipt({
    required this.unitId,
    required this.outcome,
    required this.brand,
    required this.batchNumber,
    required this.checkedAt,
    required this.firstVerification,
  });

  Map<String, dynamic> toJson() => {
        'unit_id': unitId,
        'outcome': outcome,
        'brand': brand,
        'batch_number': batchNumber,
        'checked_at': checkedAt.toIso8601String(),
        'first': firstVerification,
      };

  static Receipt fromJson(Map<String, dynamic> json) => Receipt(
        unitId: json['unit_id'] as String? ?? '',
        outcome: json['outcome'] as String? ?? '',
        brand: json['brand'] as String? ?? '',
        batchNumber: json['batch_number'] as String? ?? '',
        checkedAt:
            DateTime.tryParse(json['checked_at'] as String? ?? '') ?? DateTime.now(),
        firstVerification: json['first'] as bool? ?? false,
      );
}

class SessionStore {
  SessionStore({FlutterSecureStorage? secure})
      : _secure = secure ?? const FlutterSecureStorage();

  final FlutterSecureStorage _secure;

  Future<String?> readCredential() => _secure.read(key: _credentialKey);

  Future<void> writeCredential(String credential) =>
      _secure.write(key: _credentialKey, value: credential);

  Future<void> clearCredential() => _secure.delete(key: _credentialKey);

  Future<List<Receipt>> readReceipts() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_receiptsKey) ?? const [];
    return raw
        .map((entry) => Receipt.fromJson(json.decode(entry) as Map<String, dynamic>))
        .toList()
      ..sort((a, b) => b.checkedAt.compareTo(a.checkedAt));
  }

  Future<void> addReceipt(Receipt receipt) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_receiptsKey) ?? <String>[];
    raw.add(json.encode(receipt.toJson()));
    await prefs.setStringList(_receiptsKey, raw);
  }

  /// The highest trust-manifest version this installation has accepted.
  ///
  /// It only ever increases: an older manifest is refused, so a revoked key
  /// cannot be restored by replaying one.
  Future<int> readManifestVersion() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getInt(_manifestVersionKey) ?? 0;
  }

  Future<void> writeManifestVersion(int version) async {
    final prefs = await SharedPreferences.getInstance();
    final current = prefs.getInt(_manifestVersionKey) ?? 0;
    if (version > current) await prefs.setInt(_manifestVersionKey, version);
  }
}
