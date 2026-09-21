/// App attestation: the `X-App-Check` token every consumer request carries.
///
/// The backend requires attestation *and* a session credential on every
/// consumer endpoint, and treats a missing or bad token as an authentication
/// failure. This file is the app's half of that: a real Play Integrity token
/// from Firebase App Check.
///
/// It fails closed. A release build that was not given a Firebase project, or
/// that cannot obtain a token, refuses to produce one rather than sending
/// something the server might be configured to wave through. The development
/// placeholder is only ever returned by a debug or profile build, and the
/// production backend rejects it in any case (`APP_CHECK_MODE=firebase`).
library;

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

/// Raised when no attestation token can be produced.
///
/// Carries a static reason for the log; never a token, and never anything
/// derived from one.
class AttestationUnavailable implements Exception {
  final String reason;
  AttestationUnavailable(this.reason);
  @override
  String toString() => 'AttestationUnavailable: $reason';
}

/// Firebase project identifiers, supplied at build time with `--dart-define`.
///
/// They are not secrets — an APK carries them in the clear either way — but
/// they are environment-specific, so they are not committed. Supplying them
/// through defines rather than `google-services.json` keeps the build working
/// for anyone without the file, and keeps the pilot and production projects
/// apart by build command rather than by a file someone has to remember to
/// swap.
const firebaseProjectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
const firebaseAppId = String.fromEnvironment('FIREBASE_APP_ID');
const firebaseApiKey = String.fromEnvironment('FIREBASE_API_KEY');
const firebaseSenderId = String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');

/// `play-integrity` in production; `debug` only for emulator work, where a
/// token is registered by hand in the Firebase console.
const appCheckProvider =
    String.fromEnvironment('APP_CHECK_PROVIDER', defaultValue: 'play-integrity');

/// The token a development build sends when no Firebase project is configured.
///
/// The development backend's `accept-any` mode takes it. A production backend
/// refuses it, and so does a release build of this app.
const developmentToken = 'dev-token';

bool get isAttestationConfigured =>
    firebaseProjectId.isNotEmpty &&
    firebaseAppId.isNotEmpty &&
    firebaseApiKey.isNotEmpty &&
    firebaseSenderId.isNotEmpty;

Future<void>? _initialisation;

/// Returns an App Check token, or throws [AttestationUnavailable].
///
/// Every failure below is a refusal to verify, not a verification result: the
/// caller turns it into "Unable to verify on this device."
Future<String> attestationToken() async {
  if (!isAttestationConfigured) {
    if (kReleaseMode) {
      throw AttestationUnavailable(
        'this build has no Firebase project; rebuild with the '
        'FIREBASE_* dart-defines (see consumer-app/README.md)',
      );
    }
    return developmentToken;
  }

  try {
    await _ensureInitialised();
    final token = await FirebaseAppCheck.instance.getToken();
    if (token == null || token.isEmpty) {
      throw AttestationUnavailable('App Check returned no token');
    }
    return token;
  } on AttestationUnavailable {
    rethrow;
  } catch (error) {
    // Play Integrity is unavailable on devices without Play Services, and on
    // rooted or otherwise unattested ones. That is the SRS's hard stop, not an
    // error to retry silently.
    throw AttestationUnavailable('App Check failed: ${error.runtimeType}');
  }
}

/// Starts Firebase once, and lets a failed start be retried.
Future<void> _ensureInitialised() async {
  final started = _initialisation;
  if (started != null) return started;
  final attempt = _initialise();
  _initialisation = attempt;
  try {
    await attempt;
  } catch (_) {
    // Play Services can recover between scans; do not cache the failure.
    _initialisation = null;
    rethrow;
  }
}

Future<void> _initialise() async {
  if (Firebase.apps.isEmpty) {
    await Firebase.initializeApp(
      options: const FirebaseOptions(
        apiKey: firebaseApiKey,
        appId: firebaseAppId,
        messagingSenderId: firebaseSenderId,
        projectId: firebaseProjectId,
      ),
    );
  }
  // Android only. iOS needs its own attestation and device testing, and is
  // deferred (doc 09).
  await FirebaseAppCheck.instance.activate(providerAndroid: _androidProvider);
}

AndroidAppCheckProvider get _androidProvider => switch (appCheckProvider) {
      'play-integrity' => const AndroidPlayIntegrityProvider(),
      // Debug tokens are registered by hand and bypass Play Integrity, so a
      // release build must never use one.
      'debug' when !kReleaseMode => const AndroidDebugProvider(),
      'debug' => throw AttestationUnavailable(
          'the App Check debug provider is not allowed in a release build',
        ),
      _ => throw AttestationUnavailable(
          'unknown APP_CHECK_PROVIDER: expected play-integrity or debug',
        ),
    };

/// Reset for tests. Not used by the app.
@visibleForTesting
void resetAttestationForTest() => _initialisation = null;
