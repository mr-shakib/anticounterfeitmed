/// The screens render, in both themes and both languages, at phone size.
///
/// Besides catching layout overflow, these pin the two presentation rules that
/// matter most: every result shows its fixed wording, and a successful result
/// always carries the clarification that it checks a record, not the medicine.
library;

import 'dart:convert';

import 'package:consumer_app/app_state.dart';
import 'package:consumer_app/core/outcomes.dart';
import 'package:consumer_app/data/api_client.dart';
import 'package:consumer_app/data/session_store.dart';
import 'package:consumer_app/l10n/strings.dart';
import 'package:consumer_app/screens/history_screen.dart';
import 'package:consumer_app/screens/package_screen.dart';
import 'package:consumer_app/screens/report_screen.dart';
import 'package:consumer_app/screens/result_screen.dart';
import 'package:consumer_app/ui/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _package = PackageDetails(
  brand: 'Napa Extra',
  generic: 'Paracetamol + Caffeine',
  strength: '500 mg + 65 mg',
  dosageForm: 'Tablet',
  packDescription: 'Strip of 10 tablets',
  batchNumber: 'BN-2026-0042',
  manufacturedOn: '2026-09-01',
  expiresOn: '2028-08-31',
);

Future<void> _pump(
  WidgetTester tester,
  Widget screen, {
  ThemeMode mode = ThemeMode.light,
  AppLanguage language = AppLanguage.english,
  Size size = const Size(360, 780),
  bool settle = true,
}) async {
  tester.view.physicalSize = size * 3;
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);

  final state = AppState()..setLanguage(language);
  await tester.pumpWidget(
    AppScope(
      state: state,
      child: MaterialApp(
        theme: lightTheme(),
        darkTheme: darkTheme(),
        themeMode: mode,
        home: screen,
      ),
    ),
  );
  if (settle) {
    await tester.pumpAndSettle();
  } else {
    // A spinner never settles; give async work and a few frames a chance.
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
  }
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('bn');
    await initializeDateFormatting('en');
  });
  setUp(() => SharedPreferences.setMockInitialValues({}));

  group('result', () {
    for (final language in AppLanguage.values) {
      for (final mode in [ThemeMode.light, ThemeMode.dark]) {
        testWidgets('every outcome, ${language.name}, ${mode.name}', (tester) async {
          final s = Strings(language);
          for (final outcome in Outcome.values) {
            await _pump(
              tester,
              ResultScreen(
                outcome: outcome,
                checkedAt: DateTime.utc(2026, 10, 14, 9, 30),
                firstVerification: outcome == Outcome.verifiedFirst,
              ),
              mode: mode,
              language: language,
            );
            expect(find.text(s.resultText(outcome)), findsOneWidget, reason: outcome.name);
            expect(
              find.text(s.contentsClarification),
              outcome.showsPackage ? findsOneWidget : findsNothing,
              reason: '${outcome.name}: the clarification goes with every success, and only there',
            );
          }
        });
      }
    }

    testWidgets('a pending receipt says so', (tester) async {
      await _pump(
        tester,
        ResultScreen(
          outcome: Outcome.verifiedFirst,
          checkedAt: DateTime.now(),
          firstVerification: true,
          pendingReceipt: true,
        ),
        settle: false,
      );
      expect(find.text(const Strings(AppLanguage.english).pendingReceipt), findsOneWidget);
    });
  });

  group('package', () {
    testWidgets('an eligible code offers the check and says what it records', (tester) async {
      const s = Strings(AppLanguage.english);
      await _pump(
        tester,
        const PackageScreen(
          prepared: PrepareResult(
            outcome: Outcome.verifiedFirst,
            unitId: 'u1',
            challengeId: 'c1',
            package: _package,
          ),
        ),
      );
      expect(find.text('Napa Extra'), findsOneWidget);
      expect(find.text(s.verifyAction), findsOneWidget);
      expect(find.text(s.verifyExplanation), findsOneWidget);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      testWidgets('a recall leads, and nothing can be confirmed (${mode.name})', (tester) async {
        for (final language in AppLanguage.values) {
          final s = Strings(language);
          await _pump(
            tester,
            const PackageScreen(
              prepared: PrepareResult(outcome: Outcome.recalled, package: _package),
            ),
            mode: mode,
            language: language,
          );
          expect(find.text(s.resultText(Outcome.recalled)), findsOneWidget);
          expect(find.text(s.verifyAction), findsNothing);
        }
      });
    }
  });

  group('medicine information', () {
    const sections = [
      InformationSection('indications', 'Peptic ulcer diseases'),
      InformationSection('dosage_administration', '40 mg daily in the morning.'),
    ];

    test('only known, well-formed sections are kept, in order', () {
      final kept = informationFrom({
        'product_information': [
          {'field': 'indications', 'text': ' Peptic ulcer '},
          {'field': 'cure_rate', 'text': '100%'},
          {'field': 'side_effects'},
          'not an entry',
          {'field': 'storage_conditions', 'text': 'Keep dry.'},
        ],
      });
      expect(kept.map((e) => e.field), ['indications', 'storage_conditions']);
      expect(kept.first.text, 'Peptic ulcer');
      expect(informationFrom({}), isEmpty);
    });

    for (final language in AppLanguage.values) {
      testWidgets('shown with its source and the physician advice (${language.name})',
          (tester) async {
        final s = Strings(language);
        await _pump(
          tester,
          const PackageScreen(
            prepared: PrepareResult(
              outcome: Outcome.verifiedFirst,
              unitId: 'u1',
              challengeId: 'c1',
              package: _package,
              information: sections,
            ),
          ),
          language: language,
        );
        await tester.scrollUntilVisible(find.text(s.physicianAdvice), 200,
            scrollable: find.byType(Scrollable).first);
        expect(find.text(s.informationTitle), findsOneWidget);
        expect(find.text(s.informationSource), findsOneWidget);
        expect(find.text(s.informationHeading('indications')!), findsOneWidget);
        // The first section starts open.
        expect(find.text('Peptic ulcer diseases'), findsOneWidget);
      });
    }

    testWidgets('absent when the manufacturer gave none', (tester) async {
      const s = Strings(AppLanguage.english);
      await _pump(
        tester,
        const PackageScreen(
          prepared: PrepareResult(
            outcome: Outcome.verifiedFirst,
            unitId: 'u1',
            challengeId: 'c1',
            package: _package,
          ),
        ),
      );
      expect(find.text(s.informationTitle), findsNothing);
    });

    testWidgets('still there after the check is recorded', (tester) async {
      const s = Strings(AppLanguage.english);
      await _pump(
        tester,
        ResultScreen(
          outcome: Outcome.verifiedFirst,
          checkedAt: DateTime.now(),
          firstVerification: true,
          information: sections,
        ),
        mode: ThemeMode.dark,
      );
      await tester.scrollUntilVisible(find.text(s.informationTitle), 200,
          scrollable: find.byType(Scrollable).first);
      expect(find.text(s.informationTitle), findsOneWidget);
      // The clarification still leads, above the information.
      expect(find.text(s.contentsClarification), findsOneWidget);
    });
  });

  group('history', () {
    testWidgets('empty', (tester) async {
      await _pump(tester, const HistoryScreen(), settle: false);
      expect(find.text(const Strings(AppLanguage.english).noHistory), findsOneWidget);
    });

    testWidgets('each receipt shows its original check time', (tester) async {
      final receipt = Receipt(
        unitId: 'u1',
        outcome: Outcome.verifiedFirst.name,
        brand: 'Napa Extra',
        batchNumber: 'BN-2026-0042',
        checkedAt: DateTime.utc(2026, 10, 14, 9, 30),
        firstVerification: true,
      );
      SharedPreferences.setMockInitialValues({
        'verification_receipts': [json.encode(receipt.toJson())],
      });
      for (final language in AppLanguage.values) {
        await _pump(tester, const HistoryScreen(),
            language: language, mode: ThemeMode.dark, settle: false);
        final s = Strings(language);
        expect(find.text(s.historyNotice), findsOneWidget);
        expect(find.textContaining('${s.checkedAt}: '), findsOneWidget);
      }
    });
  });

  testWidgets('report', (tester) async {
    for (final language in AppLanguage.values) {
      await _pump(tester, const ReportScreen(externalReference: 'BN-2026-0042-000014'),
          language: language, size: const Size(320, 640));
      expect(find.text('BN-2026-0042-000014'), findsOneWidget);
    }
  });

  group('appearance', () {
    test('light is the default, whatever the phone is set to', () async {
      final state = AppState();
      expect(state.themeMode, ThemeMode.light);
      await state.restorePreferences();
      expect(state.themeMode, ThemeMode.light);
    });

    test('a chosen appearance and language are remembered', () async {
      AppState()
        ..setThemeMode(ThemeMode.dark)
        ..setLanguage(AppLanguage.bangla);
      await Future<void>.delayed(Duration.zero);

      final restored = AppState();
      await restored.restorePreferences();
      expect(restored.themeMode, ThemeMode.dark);
      expect(restored.language, AppLanguage.bangla);
    });
  });
}
