/// The consumer app.
///
/// What this app tells someone is deliberately narrow: whether a scanned code
/// matches a manufacturer's signed record. It never says the medicine is
/// genuine or safe, it never asks for location, and it shows nothing about
/// anyone else's checks.
library;

import 'package:flutter/material.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'app_state.dart';
import 'screens/scan_screen.dart';
import 'ui/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Bundled locale data for dates in Bangla; nothing is fetched.
  await initializeDateFormatting('bn');
  await initializeDateFormatting('en');
  runApp(const AnticounterfeitMedApp());
}

class AnticounterfeitMedApp extends StatefulWidget {
  const AnticounterfeitMedApp({super.key});

  @override
  State<AnticounterfeitMedApp> createState() => _AnticounterfeitMedAppState();
}

class _AnticounterfeitMedAppState extends State<AnticounterfeitMedApp> {
  final AppState _state = AppState();

  @override
  void initState() {
    super.initState();
    _state.restorePreferences();
  }

  @override
  void dispose() {
    _state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: _state,
      child: ListenableBuilder(
        listenable: _state,
        builder: (context, _) => MaterialApp(
          title: 'Anticounterfeit Med',
          debugShowCheckedModeBanner: false,
          theme: lightTheme(),
          darkTheme: darkTheme(),
          // Light by default. Dark, or following the phone, is a choice made
          // in Settings.
          themeMode: _state.themeMode,
          home: const ScanScreen(),
        ),
      ),
    );
  }
}
