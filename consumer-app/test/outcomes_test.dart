/// Outcome semantics and the wording attached to them.
library;

import 'package:consumer_app/core/outcomes.dart';
import 'package:consumer_app/l10n/strings.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('only an eligible first check offers confirmation', () {
    for (final outcome in Outcome.values) {
      expect(outcome.canConfirm, outcome == Outcome.verifiedFirst,
          reason: outcome.name);
    }
  });

  test('restrictions are never presented as positive', () {
    for (final outcome in [Outcome.recalled, Outcome.restricted, Outcome.expired]) {
      expect(outcome.isPositive, isFalse, reason: outcome.name);
      expect(outcome.isRestriction, isTrue, reason: outcome.name);
      expect(outcome.canConfirm, isFalse, reason: outcome.name);
    }
  });

  test('unknown wire values fall back to service unavailable', () {
    expect(Outcome.fromWire('SOMETHING_NEW'), Outcome.serviceUnavailable);
    expect(Outcome.fromWire(null), Outcome.serviceUnavailable);
  });

  group('wording', () {
    final english = const Strings(AppLanguage.english);
    final bangla = const Strings(AppLanguage.bangla);

    test('every outcome has text in both languages', () {
      for (final outcome in Outcome.values) {
        expect(english.resultText(outcome).trim(), isNotEmpty, reason: outcome.name);
        expect(bangla.resultText(outcome).trim(), isNotEmpty, reason: outcome.name);
        expect(english.resultText(outcome), isNot(equals(bangla.resultText(outcome))),
            reason: '${outcome.name} is not translated');
      }
    });

    test('no result claims the medicine is genuine or safe', () {
      // The distinction this protects is the whole point of the clarification.
      const forbidden = ['genuine', 'safe', 'authentic', '100%'];
      for (final outcome in Outcome.values) {
        final text = english.resultText(outcome).toLowerCase();
        for (final word in forbidden) {
          expect(text.contains(word), isFalse,
              reason: '${outcome.name} says "$word"');
        }
      }
    });

    test('the contents clarification exists in both languages', () {
      expect(english.contentsClarification, contains('does not test'));
      expect(bangla.contentsClarification.trim(), isNotEmpty);
      expect(bangla.contentsClarification,
          isNot(equals(english.contentsClarification)));
    });

    test('a successful result is the one that must carry the clarification', () {
      expect(Outcome.verifiedFirst.showsPackage, isTrue);
      expect(Outcome.previouslyVerified.showsPackage, isTrue);
    });
  });
}
