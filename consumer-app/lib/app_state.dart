/// Application-wide state: language, session, and the API client.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'data/api_client.dart';
import 'data/session_store.dart';
import 'l10n/strings.dart';

/// The offline root public key, compiled into the app.
///
/// Everything else the app trusts is authorised by a manifest this key signs,
/// so replacing it requires a separately authenticated app update -- which is
/// exactly the property that makes it worth shipping in the binary.
///
/// Replaced at build time for each environment. This development value is the
/// key the local stack provisions.
const rootPublicKeyBase64 = String.fromEnvironment(
  'ROOT_PUBLIC_KEY',
  defaultValue: '',
);

const backendBaseUrl = String.fromEnvironment(
  'BACKEND_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

class AppState extends ChangeNotifier {
  AppState({SessionStore? store, ApiClient? client})
      : sessionStore = store ?? SessionStore() {
    _client = client;
  }

  final SessionStore sessionStore;
  ApiClient? _client;

  AppLanguage _language = AppLanguage.english;
  AppLanguage get language => _language;
  Strings get strings => Strings(_language);

  void toggleLanguage() {
    _language =
        _language == AppLanguage.english ? AppLanguage.bangla : AppLanguage.english;
    notifyListeners();
  }

  ApiClient get client {
    final existing = _client;
    if (existing != null) return existing;
    final created = ApiClient(
      baseUrl: backendBaseUrl,
      rootPublicKey: rootPublicKeyBase64.isEmpty
          ? Uint8List(0)
          : base64.decode(rootPublicKeyBase64),
      sessionStore: sessionStore,
    );
    _client = created;
    return created;
  }
}

/// Inherited access to [AppState] without adding a state-management package.
class AppScope extends InheritedNotifier<AppState> {
  const AppScope({super.key, required AppState state, required super.child})
      : super(notifier: state);

  static AppState of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope is missing above this widget');
    return scope!.notifier!;
  }
}
