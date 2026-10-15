/// Application-wide state: language, session, and the API client.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

  static const _languageKey = 'ui.language';
  static const _themeKey = 'ui.theme';

  AppLanguage _language = AppLanguage.english;
  AppLanguage get language => _language;
  Strings get strings => Strings(_language);

  /// Light unless the person chooses otherwise in Settings -- not whatever the
  /// phone happens to be set to.
  ThemeMode _themeMode = ThemeMode.light;
  ThemeMode get themeMode => _themeMode;

  /// Restore the language and appearance chosen last time. Display settings
  /// only: nothing here is a credential or a record.
  Future<void> restorePreferences() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final language = prefs.getString(_languageKey);
      final theme = prefs.getString(_themeKey);
      _language = AppLanguage.values.firstWhere(
        (l) => l.name == language,
        orElse: () => _language,
      );
      _themeMode = ThemeMode.values.firstWhere(
        (m) => m.name == theme,
        orElse: () => _themeMode,
      );
      notifyListeners();
    } catch (_) {
      // Defaults are fine; a preference is not worth failing over.
    }
  }

  void setLanguage(AppLanguage language) {
    if (language == _language) return;
    _language = language;
    notifyListeners();
    _save(_languageKey, language.name);
  }

  void toggleLanguage() => setLanguage(
        _language == AppLanguage.english ? AppLanguage.bangla : AppLanguage.english,
      );

  void setThemeMode(ThemeMode mode) {
    if (mode == _themeMode) return;
    _themeMode = mode;
    notifyListeners();
    _save(_themeKey, mode.name);
  }

  Future<void> _save(String key, String value) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(key, value);
    } catch (_) {}
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
