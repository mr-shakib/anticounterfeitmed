/// User-facing text, in English and Bangla.
///
/// The result wording is fixed by docs/09 and must not be improvised. The
/// distinction it protects is that this service checks a *digital record*, not
/// the medicine itself, and the Bangla must preserve that distinction as
/// carefully as the English does.
///
/// The Bangla here is a working draft for development. It needs review by a
/// native speaker with pharmaceutical context before any pilot (decision D10);
/// a translation that blurs "the code matches" into "the medicine is genuine"
/// is a patient-safety defect, not a wording preference.
library;

import '../core/outcomes.dart';

enum AppLanguage { english, bangla }

class Strings {
  final AppLanguage language;
  const Strings(this.language);

  bool get _bn => language == AppLanguage.bangla;

  String _pick(String en, String bn) => _bn ? bn : en;

  // --- shell ---------------------------------------------------------------
  String get appName => 'Anticounterfeit Med';
  String get scanTitle => _pick('Scan the code', 'কোডটি স্ক্যান করুন');
  String get historyTitle => _pick('My checks', 'আমার যাচাইসমূহ');
  String get reportTitle => _pick('Report a concern', 'উদ্বেগ জানান');
  String get help => _pick('Help', 'সহায়তা');
  String get close => _pick('Close', 'বন্ধ করুন');
  String get retry => _pick('Try again', 'আবার চেষ্টা করুন');
  String get cancel => _pick('Cancel', 'বাতিল');

  // --- scanning ------------------------------------------------------------
  String get scanInstruction => _pick(
        'Scratch off the silver coating on the strip, then point the camera at the code.',
        'স্ট্রিপের রুপালি আবরণ ঘষে তুলুন, তারপর ক্যামেরাটি কোডের দিকে ধরুন।',
      );
  String get torch => _pick('Light', 'আলো');
  String get notOurCode => _pick(
        'That is not an Anticounterfeit Med code.',
        'এটি Anticounterfeit Med কোড নয়।',
      );
  String get cameraUnavailable => _pick(
        'The camera is not available.',
        'ক্যামেরা ব্যবহার করা যাচ্ছে না।',
      );
  String get cameraHelp => _pick(
        'Allow camera access in Settings, then reopen this screen. '
            'You can still report a concern using the reference printed on the strip.',
        'সেটিংসে ক্যামেরার অনুমতি দিন, তারপর এই পাতাটি আবার খুলুন। '
            'স্ট্রিপে ছাপানো রেফারেন্স ব্যবহার করে আপনি এখনো উদ্বেগ জানাতে পারেন।',
      );
  String get checking => _pick('Checking…', 'যাচাই করা হচ্ছে…');

  // --- package preview -----------------------------------------------------
  String get packageTitle => _pick('Package details', 'প্যাকেটের তথ্য');
  String get brand => _pick('Brand', 'ব্র্যান্ড');
  String get generic => _pick('Generic name', 'জেনেরিক নাম');
  String get strength => _pick('Strength', 'মাত্রা');
  String get dosageForm => _pick('Form', 'ধরন');
  String get packDescription => _pick('Pack', 'প্যাক');
  String get manufacturer => _pick('Manufacturer', 'প্রস্তুতকারক');
  String get batch => _pick('Batch', 'ব্যাচ');
  String get manufacturedOn => _pick('Manufactured', 'প্রস্তুতের তারিখ');
  String get expiresOn => _pick('Expires', 'মেয়াদ শেষ');

  String get verifyAction => _pick('Verify this package', 'এই প্যাকেটটি যাচাই করুন');
  String get verifyExplanation => _pick(
        'This records a check. It does not record a sale.',
        'এটি একটি যাচাই নথিভুক্ত করে। এটি কোনো বিক্রয় নথিভুক্ত করে না।',
      );

  // --- the mandatory clarification ----------------------------------------
  /// Shown with every successful result. Required by docs/09.
  String get contentsClarification => _pick(
        'This checks the code’s digital record; it does not test the medicine’s contents.',
        'এটি কোডের ডিজিটাল রেকর্ড যাচাই করে; এটি ওষুধের উপাদান পরীক্ষা করে না।',
      );

  // --- results -------------------------------------------------------------
  String resultText(Outcome outcome) => switch (outcome) {
        Outcome.verifiedFirst => _pick(
            'Code matches the manufacturer’s record. First verification recorded.',
            'কোডটি প্রস্তুতকারকের রেকর্ডের সঙ্গে মিলেছে। প্রথম যাচাই নথিভুক্ত হয়েছে।',
          ),
        Outcome.notActivated => _pick(
            'This code has not been activated by the manufacturer.',
            'এই কোডটি প্রস্তুতকারক কর্তৃক সক্রিয় করা হয়নি।',
          ),
        Outcome.previouslyVerified => _pick(
            'This code was previously verified. This additional check has been recorded.',
            'এই কোডটি পূর্বে যাচাই করা হয়েছে। এই অতিরিক্ত যাচাইটি নথিভুক্ত হয়েছে।',
          ),
        Outcome.notFound => _pick(
            'Code not found in this system.',
            'এই সিস্টেমে কোডটি পাওয়া যায়নি।',
          ),
        Outcome.expired => _pick(
            'The recorded expiry date has passed.',
            'নথিভুক্ত মেয়াদ শেষের তারিখ পেরিয়ে গেছে।',
          ),
        Outcome.recalled => _pick(
            'This batch has been recalled. View the recall details.',
            'এই ব্যাচটি প্রত্যাহার করা হয়েছে। প্রত্যাহারের বিবরণ দেখুন।',
          ),
        Outcome.restricted => _pick(
            'Verification is restricted. Contact support.',
            'যাচাই সীমাবদ্ধ করা হয়েছে। সহায়তার সঙ্গে যোগাযোগ করুন।',
          ),
        Outcome.invalidCredential => _pick(
            'Unable to validate the manufacturer’s record.',
            'প্রস্তুতকারকের রেকর্ড যাচাই করা যায়নি।',
          ),
        Outcome.serviceUnavailable => _pick(
            'Unable to complete verification. Please retry.',
            'যাচাই সম্পন্ন করা যায়নি। অনুগ্রহ করে আবার চেষ্টা করুন।',
          ),
        Outcome.attestationFailed => _pick(
            'Unable to verify on this device.',
            'এই ডিভাইসে যাচাই করা যাচ্ছে না।',
          ),
        Outcome.offline => _pick(
            'Connect to check current status.',
            'বর্তমান অবস্থা জানতে ইন্টারনেটে সংযুক্ত হোন।',
          ),
      };

  String get checkedAt => _pick('Checked', 'যাচাইয়ের সময়');
  String get firstVerificationRecorded =>
      _pick('First verification recorded', 'প্রথম যাচাই নথিভুক্ত');
  String get pendingReceipt => _pick(
        'Recorded. Waiting for the signed receipt…',
        'নথিভুক্ত হয়েছে। স্বাক্ষরিত রসিদের অপেক্ষায়…',
      );

  // --- history -------------------------------------------------------------
  String get noHistory => _pick(
        'You have not checked any packages yet.',
        'আপনি এখনো কোনো প্যাকেট যাচাই করেননি।',
      );
  String get historyNotice => _pick(
        'These are your own past checks, with the time each was made. Refresh to see current status.',
        'এগুলো আপনার নিজের আগের যাচাই, প্রতিটির সময়সহ। বর্তমান অবস্থা দেখতে রিফ্রেশ করুন।',
      );
  String get refreshStatus => _pick('Refresh status', 'অবস্থা রিফ্রেশ করুন');

  // --- reporting -----------------------------------------------------------
  String get reportReason => _pick('What is the concern?', 'উদ্বেগটি কী?');
  String get reportDescription => _pick('Describe it (optional)', 'বর্ণনা করুন (ঐচ্ছিক)');
  String get reportReference => _pick(
        'Printed reference on the strip (optional)',
        'স্ট্রিপে ছাপানো রেফারেন্স (ঐচ্ছিক)',
      );
  String get reportPharmacy => _pick(
        'Pharmacy name (optional)',
        'ফার্মেসির নাম (ঐচ্ছিক)',
      );
  String get submitReport => _pick('Send report', 'রিপোর্ট পাঠান');
  String get reportFiled => _pick('Report received. Case number:', 'রিপোর্ট গৃহীত। কেস নম্বর:');

  String reasonLabel(String code) => switch (code) {
        'CODE_NOT_FOUND' => _pick('The code was not found', 'কোডটি পাওয়া যায়নি'),
        'ALREADY_VERIFIED' =>
          _pick('It was already verified', 'এটি আগেই যাচাই করা হয়েছে'),
        'PACKAGING_SUSPICIOUS' =>
          _pick('The packaging looks wrong', 'প্যাকেজিং সন্দেহজনক মনে হচ্ছে'),
        'SCAN_FAILED' => _pick('The code will not scan', 'কোডটি স্ক্যান হচ্ছে না'),
        _ => _pick('Something else', 'অন্য কিছু'),
      };
}
