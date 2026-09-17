/// The consumer app.
///
/// What this app tells someone is deliberately narrow: whether a scanned code
/// matches a manufacturer's signed record. It never says the medicine is
/// genuine or safe, it never asks for location, and it shows nothing about
/// anyone else's checks.
library;

import 'package:flutter/material.dart';

import 'app_state.dart';
import 'screens/scan_screen.dart';

void main() => runApp(const MedSecureApp());

class MedSecureApp extends StatefulWidget {
  const MedSecureApp({super.key});

  @override
  State<MedSecureApp> createState() => _MedSecureAppState();
}

class _MedSecureAppState extends State<MedSecureApp> {
  final AppState _state = AppState();

  @override
  void dispose() {
    _state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: _state,
      child: MaterialApp(
        title: 'MedSecure PQC',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorSchemeSeed: const Color(0xFF0B6B5E),
          useMaterial3: true,
        ),
        darkTheme: ThemeData(
          colorSchemeSeed: const Color(0xFF0B6B5E),
          brightness: Brightness.dark,
          useMaterial3: true,
        ),
        home: const ScanScreen(),
      ),
    );
  }
}
