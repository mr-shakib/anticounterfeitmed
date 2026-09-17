/// Verification outcomes, and what each one means.
///
/// The server decides the outcome; the app never infers one. The wording shown
/// for each is fixed in l10n/strings.dart and must not be improvised, because
/// the difference between "this code matches a record" and "this medicine is
/// genuine" is a patient-safety distinction.
library;

enum Outcome {
  verifiedFirst,
  previouslyVerified,
  notActivated,
  notFound,
  expired,
  recalled,
  restricted,
  invalidCredential,
  serviceUnavailable,
  attestationFailed,
  offline;

  static Outcome fromWire(String? value) => switch (value) {
        'VERIFIED_FIRST' => Outcome.verifiedFirst,
        'PREVIOUSLY_VERIFIED' => Outcome.previouslyVerified,
        'NOT_ACTIVATED' => Outcome.notActivated,
        'NOT_FOUND' => Outcome.notFound,
        'EXPIRED' => Outcome.expired,
        'RECALLED' => Outcome.recalled,
        'RESTRICTED' => Outcome.restricted,
        'INVALID_CREDENTIAL' => Outcome.invalidCredential,
        _ => Outcome.serviceUnavailable,
      };

  /// Whether this outcome means the package details can be shown at all.
  bool get showsPackage =>
      this == Outcome.verifiedFirst || this == Outcome.previouslyVerified;

  /// Whether confirming is worth offering.
  bool get canConfirm => this == Outcome.verifiedFirst;

  /// Whether this reads as reassuring. Used only for presentation.
  bool get isPositive => this == Outcome.verifiedFirst;

  /// Restrictions take priority over a positive result and must look serious.
  bool get isRestriction =>
      this == Outcome.recalled ||
      this == Outcome.restricted ||
      this == Outcome.expired;
}
