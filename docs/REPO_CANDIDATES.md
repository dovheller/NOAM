# מועמדי ריפו לפרויקט NOAM

> איחוד של שני סבבי חיפוש (2026-11-10) ושל בדיקת אימות. בסיס: סבב 1 (מפורט). מסבב 2 נוספו מועמדים ותוקנו טעויות.
> **תיקונים שאומתו מול דפי הריפו:** `whatsapp-msgstore-viewer` הוא **GPL-3.0** (סבב 2 כתב "MIT-like" — שגוי). הגרסה של KnugiHK בדף היא 0.13.0 (סבב 2 כתב "0.14 rc" — לא אומת). הדגל הוא `--enrich-from-vcards` (ברבים).
> **תיקון לסבב 1:** אפיון WhatsApp §5.1(5) **לא** טוען שאי אפשר להוריד מ-Drive; הוא מתיר פענוח של קובץ שהלקוח הוריד ידנית. ההערה על `wabdd` נכונה כתוספת בלבד.
> **ממצא עלינו:** האפיון והריפו תכננו "להעתיק את לוגיקת ה-SQL" מ-`whatsapp-msgstore-viewer`. הוא GPL-3.0 — העתקה תהפוך את `noam_l2` ל-GPL. **בוטל:** WP11–12 נבנים על KnugiHK (MIT).

> "קומיט אחרון" לפי מה שאותר בעת הסיבוב. לפני אימוץ, לבדוק שוב בדף הריפו.

---

## 1. טבלת המועמדים

ציון: 5 = לקחת, 4 = לקחת עם הסתייגות, 3 = לבדוק, 2 = ייחוס בלבד, 1 = לא.

### WP11–WP12 · שכבה 2 — ארכיון WhatsApp

| ריפו | מה הוא עושה | מה ניקח | רישיון | קומיט אחרון | Py ≥3.11 / Ubuntu | סיכון / הסתייגות | ציון |
|---|---|---|---|---|---|---|---|
| [KnugiHK/Whatsapp-Chat-Exporter](https://github.com/KnugiHK/Whatsapp-Chat-Exporter) | פרסר `msgstore.db` לאנדרואיד ו-iOS, ייצוא HTML/JSON/TXT עם מדיה. פענוח crypt12/14/15 מובנה (pycryptodome + javaobj). **מעשיר שמות מקובץ VCF** (`--enrich-from-vcards`). תומך בסכמה החדשה. | **ספרייה / מנוע הייצוא של WP12.** תבנית HTML (Jinja2) ניתנת להחלפה, יש `--offline` ל-assets מקומיים, `--per-chat`, `--txt`. | MIT | אפריל 2026, 755 קומיטים, ~1k ⭐ | ✓ (PyPI, Python 3) | `--check-update` פונה לאינטרנט — לכבות. התבנית לא RTL — לכתוב תבנית עברית משלנו. Issue #80 (איחוד גיבויים) פתוח מ-2024, אין מימוש. | **5** |
| [ElDavoo/wa-crypt-tools](https://github.com/ElDavoo/wa-crypt-tools) | פענוח/הצפנה של crypt12/14/15, `wainfo` לקריאת כותרת. | **תהליך משנה בלבד** (`wadecrypt`, `wainfo`), לא import. | **GPL-3.0** | ~2025, ~1k ⭐ | ✓ (PyPI) | GPL: אסור לייבא לתוך `src/noam_l2/`. אם KnugiHK מפענח מספיק טוב, אפשר לוותר לגמרי. `wainfo` תומך רק ב-crypt15. | **4** |
| [absadiki/whatsapp-msgstore-viewer](https://github.com/absadiki/whatsapp-msgstore-viewer) | אפליקציית KivyMD לצפייה, עוטפת את wa-crypt-tools. | **לא להעתיק קוד** (GPL-3.0, אומת). לקריאה בלבד אם צריך להבין סכמה. | GPL-3.0 | 51 קומיטים | ✓ | GPL; UI לא RTL. KnugiHK מכסה אותו. | 1 |
| [B16f00t/whapa](https://github.com/B16f00t/whapa) | ערכת פורנזיקה: פרסר, מפענח, מוריד מ-Drive, **Whamerge**, פרסר ייצוא רשמי (Whachat). גרסה 2.00. | **ייחוס בלבד**: איך Whamerge ממזג, ואיך Whachat מפרסר ייצוא רשמי. | **אין קובץ רישיון** (= כל הזכויות שמורות) | 2025–2026, 1.7k ⭐ | דורש 3.11+ | בלי רישיון אי אפשר להעתיק קוד. GUI כבד. | 2 |
| [giacomoferretti/whatsapp-backup-downloader-decryptor](https://github.com/giacomoferretti/whatsapp-backup-downloader-decryptor) (`wabdd`) | **מוריד גיבויים מוצפנים מקצה לקצה מ-Google Drive** ומפענח מקומית. | רעיון בלבד. ראה הערה חשובה בסעיף 2. | Apache-2.0 | 2025, 61 קומיטים, 3 ⭐ | ✓ (PyPI) | דורש אינטרנט ו-OAuth לחשבון Google של הלקוח. לא עומד ב-ADR 0003. שימוש ב-API לא מתועד של WhatsApp. | 2 |
| [cedroid/whatsapp-forensic-tool](https://github.com/cedroid/whatsapp-forensic-tool) | חילוץ ב-ADB, פענוח, צפייה, ייצוא HTML/CSV/JSON/TXT. **קיים** (תוקן מהסיבוב הקודם). | ייחוס: אסטרטגיית fallback בין סכמות (`message` ← `available_message_view` ← `messages`). | לא אותר | 2025 | 3.8+ | חילוץ ב-ADB ו-key מהמכשיר = root. קטן, מחבר יחיד. | 2 |
| [lucasrodes/whatstk](https://github.com/lucasrodes/whatstk) | פרסר **ייצוא צ'אט רשמי** (txt/zip) ל-DataFrame, אנדרואיד ו-iOS. | ספרייה למסלול "ייצוא רשמי" (§3.1 שורה 3 באפיון). | GPL-3.0 | 2025 | 3.11+ | GPL → תהליך משנה, או להעתיק את הרגקס בלבד. תלוי ב-pandas. | 3 |
| [py-vobject/vobject](https://github.com/py-vobject/vobject) | פרסר vCard/iCalendar טהור בפייתון. | ספרייה למיפוי VCF ← מספר ← שם (אם לא משתמשים ב-VCF של KnugiHK). | Apache-2.0 | 2025, v0.9.9 | 3.9+ | API ישן (camelCase). KnugiHK כבר משתמש בו. | 4 |

**נוספו מסבב 2 (לא אומתו):** [chrrel/whatsapp-exporter](https://github.com/chrrel/whatsapp-exporter) (ייחוס, 3), [mtln/chat-export](https://github.com/mtln/chat-export) — ייצוא רשמי txt → HTML, מסלול בלי מפתח (MIT לפי סבב 2, 4).

### WP5 · דוח חתום, זמן, TPM

| ריפו | מה הוא עושה | מה ניקח | רישיון | קומיט אחרון | Py ≥3.11 / Ubuntu | סיכון / הסתייגות | ציון |
|---|---|---|---|---|---|---|---|
| [MatthiasValvekens/pyHanko](https://github.com/MatthiasValvekens/pyHanko) | **חתימה דיגיטלית אמיתית בתוך ה-PDF** (PKCS#7, PAdES B-B עד B-LTA), חותמות RFC 3161, PKCS#11, אימות. | **ספרייה.** מחליפה את החתימה החיצונית הנוכחית ב-`report/keys.py`: Adobe Reader יראה "חתום ותקף". | MIT | 2025, v0.23+, ~450 ⭐ | ✓ 3.8+ | מראה החתימה הוויזואלית "פרימיטיבי" לפי המחבר. אימות PAdES מלא עדיין ניסיוני. חתימת זמן RFC 3161 דורשת אינטרנט — לדחות לשלב איסוף יומי. | **5** |
| [opentimestamps/opentimestamps-client](https://github.com/opentimestamps/opentimestamps-client) + [python-opentimestamps](https://github.com/opentimestamps/python-opentimestamps) | חותמת זמן על hash בבלוקצ'יין ביטקוין, דרך שרתי לוח שנה ציבוריים, חינם, בלי רישום. | CLI `ots stamp` / `ots upgrade` / `ots verify` ממחשב **אחר** בסוף יום; הספרייה ליצירת proof מ-digest. | LGPL-3.0 | v0.7.2, דצמבר 2024 | ✓ | הקובץ `.ots` משלים רק אחרי אישור בבלוקצ'יין (שעות). צריך `ots upgrade` מאוחר יותר. LGPL מותר כ-import עם קישור דינמי, אבל פשוט יותר כתהליך משנה. | **4** |
| [tpm2-software/tpm2-pytss](https://github.com/tpm2-software/tpm2-pytss) | Bindings לפייתון ל-TPM 2.0 (ESAPI/FAPI), כולל פורמט TSS2 PEM. | ספרייה לחתימת ECDSA כשהמפתח ב-TPM. **קיים כחבילה ב-Ubuntu**: `python3-tpm2-pytss`. | BSD-2 | 2025, v2.3 | ✓ | API נמוך. חלופה פשוטה יותר: `tpm2-tools` (`tpm2_sign`) או `tpm2-openssl` כ-provider ל-OpenSSL, ואז pyHanko חותם דרך PKCS#11/OpenSSL. | 4 |
| [py-pdf/fpdf2](https://github.com/py-pdf/fpdf2) (כבר בתלויות) | מגרסה 2.7.8: **text shaping מובנה עם uharfbuzz, כולל אלגוריתם Bidi**. `set_text_shaping(True, direction="rtl")`. | הפעלת shaping במקום python-bidi ידני. | LGPL-3.0 | פעיל | ✓ | `python-bidi` שבתלויות כנראה מיותר. לא תואם למחרוזת `{nb}` של מספר עמודים (issue #1090). לבדוק מספרים בתוך עברית. | 4 |

### WP3–WP4 · מניפסט, אימות, יעדים

| ריפו | מה הוא עושה | מה ניקח | רישיון | קומיט אחרון | Py ≥3.11 / Ubuntu | סיכון / הסתייגות | ציון |
|---|---|---|---|---|---|---|---|
| [LibraryOfCongress/bagit-python](https://github.com/LibraryOfCongress/bagit-python) | מימוש **BagIt (RFC 8493)**: תיקיית `data/`, `manifest-sha256.txt`, `tagmanifest`, `bag-info.txt`, אימות. ברירת מחדל sha256+sha512. | **תקן למניפסט.** לאמץ את פורמט הקבצים גם אם כותבים את ה-hash בעצמנו: עורך דין או לקוח יאמתו עם כל מימוש BagIt (יש ב-Go, Java, Rust). | CC0 (נחלת הכלל) | v1.9.0, 2025 (uv/pytest) | ✓ | מניח קבצים בדיסק (לא זרם). אצלנו ה-hash מחושב בזמן `Source.stream()`, אז נכתוב את המניפסט בפורמט BagIt בעצמנו ונאמת עם bagit-python. | **5** |

### WP1, WP6 · יומן audit ושכבת פרטיות

| ריפו | מה הוא עושה | מה ניקח | רישיון | קומיט אחרון | Py ≥3.11 / Ubuntu | סיכון / הסתייגות | ציון |
|---|---|---|---|---|---|---|---|
| [auditchain (PyPI)](https://pypi.org/project/auditchain/), [waxseal](https://pypi.org/project/waxseal/), [arcaeon-ledger](https://pypi.org/project/arcaeon-ledger/) | יומני JSONL עם שרשרת hash, אימות, checkpoint. | **רעיון בלבד.** כולם נולדו ב-2025–2026 סביב סוכני AI, מחבר יחיד, בלי היסטוריה. המנגנון הוא ~80 שורות: `curr = sha256(prev + canonical_json(entry))`. | MIT | 2026 | ✓ | לא להוסיף תלות על ספרייה בת חודשים ליומן שצריך לעמוד 7 שנים. לממש ב-`session/audit.py` ולאמץ מהם את ה-checkpoint (head hash חתום) ואת ה-CLI `verify`. | 2 |

### WP7–WP8 · ממשקים

| ריפו | מה הוא עושה | מה ניקח | רישיון | קומיט אחרון | Py ≥3.11 / Ubuntu | סיכון / הסתייגות | ציון |
|---|---|---|---|---|---|---|---|
| [szimek/signature_pad](https://github.com/szimek/signature_pad) | חתימה באצבע על canvas, עקומות Bézier, `toDataURL()` / `toSVG()`. | **ספרייה** (קובץ UMD יחיד, נשמר מקומית ב-`ui/client/static/`). | MIT | יוני 2026, 12k ⭐ | — (JS) | להתאים ל-DPI גבוה לפי ה-README. את ה-hash של החתימה מחשבים בשרת. | **5** |
| [bigskysoftware/htmx](https://github.com/bigskysoftware/htmx) | אינטראקטיביות מהשרת בלי build, כולל הרחבת SSE. | קובץ JS יחיד מקומי + FastAPI. מתאים ל-ADR 0001. | 0BSD | פעיל | — | לסנכרון דו-כיווני בזמן אמת בין קונסולה וטאבלט, WebSocket של FastAPI פשוט יותר מ-SSE. | 4 |
| [cage-kiosk/cage](https://github.com/cage-kiosk/cage) | קומפוזיטור Wayland לקיוסק: אפליקציה אחת, מסך מלא, בלי יציאה. **בחבילות Ubuntu** (`apt install cage`). | התקנה בלבד: `cage -- chromium --kiosk http://localhost:8000/operator`. | MIT | 2025 (wlroots 0.19) | ✓ | אין ניהול חלונות כלל (זה היתרון). לבדוק שהדפדפן לא פותח חלונות משנה. | **5** |
| [canonical/ubuntu-frame](https://github.com/canonical/ubuntu-frame) | מעטפת קיוסק של Canonical על Mir, מופץ כ-snap, תמיכה ארוכת טווח. | חלופה ל-cage אם רוצים snap ו-Ubuntu Core. | GPL-3.0 | פעיל | ✓ (snap) | מחייב snapd ואקוסיסטם snap. כבד יותר מ-cage. GPL לא בעיה (תהליך נפרד). | 3 |
| [rtl-detect (npm)](https://www.npmjs.com/package/rtl-detect) | טבלת שפות RTL כולל `yi`. | רעיון: טבלת `dir` לפי שפה, שתי שורות קוד. | BSD-3 | — | — | לא צריך ספרייה. | 1 |

### WP2 · גישה ל-MTP

| ריפו | מה הוא עושה | מה ניקח | רישיון | קומיט אחרון | Py ≥3.11 / Ubuntu | סיכון / הסתייגות | ציון |
|---|---|---|---|---|---|---|---|
| [whoozle/android-file-transfer-linux](https://github.com/whoozle/android-file-transfer-linux) | מימוש MTP עצמאי ב-C++ **בלי libmtp**, zerocopy, ספרייה סטטית/דינמית, CLI `aft-mtp-cli`, **Python bindings**, FUSE. | **גיבוי ל-libmtp.** אם ctypes מול libmtp יישבר על טלפון מסוים, `aft-mtp-cli` כתהליך משנה הוא מסלול חלופי. גם כלי אבחון ללוח האבחון. | LGPL-2.1 | v4.5, 1.5k ⭐, 66 issues פתוחים | ✓ (ב-apt: `android-file-transfer`) | מחבר יחיד. Python bindings מתועדים מעט. LGPL מותר כתהליך משנה. | 4 |
| [emdete/python-mtp](https://github.com/emdete/python-mtp) | עטיפת Cython ל-libmtp. | ייחוס להצהרות ctypes. | — | ישן | ? | 91 קומיטים, לא נראה מתוחזק. | 1 |
| PyMTP (PyPI) | עטיפת ctypes ל-libmtp. | — | GPL-3 | **ארכיון** | ✗ | PyPI מסמן "archived". לא. | 1 |

**נוספו מסבב 2 (לא אומתו):** [vdavid/mtp-rs](https://github.com/vdavid/mtp-rs) — MTP טהור ב-Rust, בלי libmtp, כ-CLI גיבוי נוסף (MIT/Apache, חדש, 4). [Heribert17/mtp](https://github.com/Heribert17/mtp) — Windows בעיקר (3). [m32/endesive](https://github.com/m32/endesive) — חלופה ל-pyHanko, רישיון לבדוק (4). [volfpeter/fasthx](https://github.com/volfpeter/fasthx) — FastAPI + HTMX (MIT, 4).

### WP13–WP15 · איחוד מכשירים, כפילויות, סידור (סבב 3 — אומת)

ראו `docs/CONSOLIDATION_SPEC.md`. הכפילויות הוודאיות לא צריכות כלי: ה-SHA-256 כבר מחושב ב-WP3. הכלים כאן הם לסיווג, לתאריך ולכמעט-כפולים.

| ריפו | מה הוא עושה | מה ניקח | רישיון | Py / Ubuntu | סיכון | ציון |
|---|---|---|---|---|---|---|
| [ivandokov/phockup](https://github.com/ivandokov/phockup) | מסדר תמונות ווידאו לתיקיות שנה/חודש/יום לפי EXIF, עם fallback לשם קובץ ולתאריך שינוי. מעתיק (לא מזיז) כברירת מחדל, מדלג על זהים לפי checksum, `-l` ל-hard links. | **ייחוס לאלגוריתם התאריך ולתבניות שם.** לא תלות: אנחנו כבר מחזיקים אינדקס SHA ולא צריכים שיעבור על הקבצים שוב. | MIT (אומת) | Python 3 + exiftool | אין תאריך גרסה בדף | 4 |
| exiftool (Phil Harvey) | קריאת EXIF/QuickTime/XMP מכל פורמט, כולל HEIC ווידאו. | **תהליך משנה** (`exiftool -json -fast2`), באצוות. ב-Ubuntu: `libimage-exiftool-perl`. | Perl Artistic / GPL | ✓ apt | איטי בקבצים בודדים — חובה באצוות | 5 |
| [JohannesBuchner/imagehash](https://github.com/JohannesBuchner/imagehash) | pHash, dHash, wavelet, colorhash, crop-resistant. | **ספרייה** לזיהוי תמונה ↔ העותק הדחוס שלה מ-WhatsApp. | BSD-2 (אומת) | ✓ (Pillow) | סף דמיון צריך כיול על דוגמאות אמיתיות | 5 |
| [qarmin/czkawka](https://github.com/qarmin/czkawka) | כפילויות, תמונות דומות, **וידאו דומה**, קבצים פגומים. | **`czkawka_cli` כתהליך משנה** לווידאו דומה ולקבצים פגומים (שלב מאוחר). | CLI ו-GTK: MIT (אומת). Krokiet: GPL-3 — לא לגעת | Rust, בינארי | אין JSON מובנה (רק עוטפים חיצוניים); גרסה 12.0 הוכרזה כאחרונה | 3 |
| [pkolaczk/fclones](https://github.com/pkolaczk/fclones) | מוצא קבוצות קבצים זהים; מצב דיווח בלבד, פלט JSON. | **לא נחוץ** — יש לנו SHA. שימושי לבדיקת שפיות על `raw/` ולמקור מסוג "תיקייה ענקית" שלא עבר WP3. | MIT (אומת) | snap / cargo | — | 3 |
| filetype (h2non/filetype.py) | זיהוי סוג לפי magic bytes, טהור בפייתון. | **ספרייה** לסוג אמיתי (סיומת שגויה, בלי סיומת). | MIT (לאמת) | ✓ | מכסה סוגים נפוצים בלבד; `python-magic` (libmagic) כחלופה רחבה | 4 |
| libarchive-c | עטיפה ל-libarchive: ZIP, 7z, TAR, RAR (קריאה), בזרם. | **ספרייה** ל-`ArchiveSource` — ארכיון כמקור קריאה-בלבד. | CC0 (לאמת) | ✓ `libarchive13` | RAR5 מוגבל; ZIP מוצפן → דילוג עם קוד | 4 |

### WP0, WP10 · תשתית

| משאב | מה | מה ניקח | רישיון | הערה | ציון |
|---|---|---|---|---|---|
| Ubuntu autoinstall (subiquity) — [canonical/subiquity](https://github.com/canonical/subiquity), תיעוד `ubuntu.com/server/docs/install/autoinstall` | התקנה אוטומטית של Ubuntu Server/Desktop מקובץ YAML: LUKS, משתמשים, חבילות, `late-commands`. | **הדרך ל-image של העמדה** (WP10). | AGPL (הכלי), ה-YAML שלנו | רשמי של Canonical. כולל `storage: layout: {name: lvm, password: ...}` ל-LUKS. | **5** |

---

## 2. חמשת הממצאים החשובים

**1. KnugiHK/Whatsapp-Chat-Exporter הוא מנוע WP12 כמעט מוכן, ובמקרה גם מבטל את בעיית ה-GPL.**
הוא MIT, פעיל (אפריל 2026), ומפענח crypt14/15 בעצמו עם pycryptodome, כך שאפשר לייבא אותו ישירות ל-`src/noam_l2/` בלי לגעת ב-wa-crypt-tools ה-GPL. הוא כבר פותר שלוש בעיות שהאפיון שלנו תכנן לפתור מאפס: סכמה חדשה וישנה, מיפוי שמות מ-VCF (`--enrich-from-vcards`), ומצב `--offline` לנכסים מקומיים. מה שנשאר לנו: תבנית HTML בעברית RTL, מנגנון איחוד כמה גיבויים (Issue #80 פתוח אצלם, אין קוד), כיבוי `--check-update`, ובדיקה מול גרסת 2.26.x. חוסך בערך שבוע מתוך השבועיים של WP11–12.

**2. pyHanko נותן חתימה שהעולם מכיר.**
החתימה הנוכחית (ECDSA על hash, מחוץ לקובץ) נכונה קריפטוגרפית אבל אף תוכנת PDF לא מציגה אותה. pyHanko מכניס חתימת PAdES לתוך ה-PDF: Adobe Reader, Okular ו-Preview מציגים "חתום, לא שונה". זה הערך העסקי של הדוח (chain-of-custody שעורך דין מבין). הוא גם תומך PKCS#11, כך שהמעבר ל-TPM (SECURITY.md §1) יכול לעבור דרך `tpm2-pkcs11` בלי לשנות את קוד החתימה. המלצה: לאמץ ב-WP5 לפני ההקשחה, כי זה משנה את `report/keys.py` ואת `REPORT_FORMAT.md`.

**3. BagIt הוא התקן למניפסט, לא פורמט JSON פרטי.**
RFC 8493, ספריית הקונגרס, CC0, מימושים בפייתון/Go/Java/Rust. אם המניפסט של NOAM ייכתב כ-`manifest-sha256.txt` + `tagmanifest-sha256.txt` + `bag-info.txt`, כל צד שלישי יאמת אותו עם כלי סטנדרטי, בלי התוכנה שלנו. זה משרת ישירות את הטענה "עותק אומת מול המקור" בדוח. העלות: לשנות את `copy/manifest.py` כך שיכתוב שני קבצים נוספים. את ה-JSON הקיים אפשר לשמור בתוך `bag-info.txt` או לצדו.

**4. fpdf2 כבר יודע RTL לבד; python-bidi כנראה מיותר.**
מגרסה 2.7.8, `set_text_shaping(True)` מריץ uharfbuzz ואת אלגוריתם ה-Bidi של יוניקוד. זה פותר את הבעיה הקלאסית של מספרים ואנגלית בתוך משפט עברי, שעיבוד ידני עם python-bidi נוטה לשבור. לבדוק ב-WP5: להפעיל shaping, להסיר את python-bidi, ולבדוק את טבלת הספירות (מספרים) ואת שמות הקבצים הלועזיים בדוח.

**5. גיבוי מ-Google Drive כן ניתן להורדה, אבל לא בעמדה. תיקון לאפיון.**
`wabdd` (Apache-2.0) מוריד גיבויים מוצפנים מקצה לקצה מ-Drive ומפענח עם מפתח 64 התווים. סעיף 5.1(5) באפיון שלנו טוען שזה בלתי אפשרי. הטענה המדויקת: **אפשרי טכנית, אסור תפעולית ל-NOAM.** זה דורש אינטרנט (סותר ADR 0003), כניסה לחשבון Google של הלקוח במכשיר של NOAM, ושימוש ב-API לא מתועד שעלול להישבר בכל רגע. להשאיר כהערת "קיים, לא בשירות", ולתקן את ניסוח הסעיף.

---

## 3. מה חיפשתי ולא מצאתי

- **כלי מוכן שמאחד כמה מכשירים לתיקייה אחת עם רשימת מוצא לכל קובץ.** יש מסדרי תמונות (phockup, elodie, digiKam) ומוצאי כפילויות (fclones, czkawka), אבל אף אחד לא שומר "מאיפה כל עותק הגיע" ולא מטפל ב-WhatsApp כמבנה. **נבנה בעצמנו** (WP14), על האינדקס שכבר קיים.
- **איחוד כמה `msgstore.db` לארכיון אחד.** אין מימוש פתוח ברובד הקריאה. whapa/Whamerge עושה מיזוג ברובד המסד (והוא בלי רישיון). KnugiHK פתח issue ולא מימש. **נממש בעצמנו** ב-`noam_l2/export.py`: איחוד לפי `key_id` + `timestamp`, קל יחסית כי אין צורך בתאימות לוואטסאפ.
- **תיעוד סכמה של msgstore.db לפי גרסה.** אין ריפו שמחזיק schema dumps לפי גרסת WhatsApp. יש מאמרי פורנזיקה (Belkasoft, Group-IB) שמתארים טבלאות, אבל לא כקוד. **נתחיל ארכיון `.schema` משלנו** בכל מסד שעובר בעמדה (ספירות וטבלאות בלבד, בלי תוכן).
- **ספריית i18n עם לוקאל יידיש אמיתי.** CLDR מכיר `yi` וכל הספריות הגדולות (Babel, ICU) יודעות שהוא RTL, אבל אין קובצי תרגום מוכנים, ואין כללי רבים/תאריכים מלאים. **הגישה: קובצי JSON משלנו לחמש השפות, `dir="rtl"` ל-`he` ו-`yi`, תאריכים בפורמט מספרי אחיד** כדי לא להסתמך על לוקאל.
- **מנגנון מוכח להבדלה בין "נכתב לתיקיית סנכרון" ל-"סונכרן לענן".** אין ספרייה כללית; זה תלוי ספק (Google Drive for Desktop, OneDrive, Dropbox חושפים סטטוס דרך תכונות קבצים או API). **לתכנן ב-WP4 בדיקה לכל ספק בנפרד**, או להגביל יעדי ענן לשלב מאוחר.
- **ספריית audit log בוגרת לפייתון.** כל מה שקיים צעיר (2025–2026). אין "sqlite-ledger" מוכר. מימוש עצמי.
- **עטיפת libmtp פייתונית מתוחזקת.** אין. ctypes שכבר נכתב הוא הדרך, עם `aft-mtp-cli` כגיבוי.

---

## 4. סימני אזהרה — פופולרי, ואסור לקחת

| ריפו / רעיון | למה לא |
|---|---|
| **KnugiHK/WhatsApp-Key-DB-Extractor** | מופיע ב-README של KnugiHK עצמו כאפשרות. מתבסס על התקנת גרסת legacy של WhatsApp; WhatsApp חוסמת גרסאות ישנות. גם אם יעבוד פעם, זה שינוי במכשיר הלקוח (הסרה והתקנה של האפליקציה) = שבירת העיקרון "המקור לא משתנה". |
| **B16f00t/whapa** | 1.7k כוכבים, נראה כמו "הכל כלול". **אין קובץ רישיון** = אסור להעתיק שורה. גם ה-GUI אינו מתאים. |
| **wabdd / Whagodri (הורדה מ-Drive)** | עובד, אבל דורש אינטרנט + חשבון Google של הלקוח במכשיר שלנו. סותר ADR 0003 ואת מודל הפרטיות. |
| **פענוח crypt14 "בלי key" / `waguess`** | `waguess` של wa-crypt-tools הוא ניסיון heuristic ולא פריצה, אבל כל הצעה ללקוח של "ננסה בלי מפתח" סותרת את §1 באפיון. לא בשירות. |
| **ספריות audit-log לסוכני AI (waxseal, arcaeon, auditchain)** | נראות מושקעות, אבל בנות חודשים, מחבר יחיד, ממוקדות ב-AI. יומן שצריך להחזיק 7 שנים לא נשען עליהן. |
| **PyMTP** | מסומן archived ב-PyPI. |
| **KnugiHK `--check-update`** | דגל שפונה לאינטרנט. חייב להיות כבוי בקוד, לא רק בתיעוד. |
| **פתרונות דפדפן ל-MTP (WebUSB)** | לא נמצאו מועמדים רלוונטיים, וגם אם יימצאו: סותר ADR 0001. |

---

## 5. לא אומת (לא נכנס לטבלה הראשית)

- `wagui` — לא נמצא ריפו בשם הזה. ייתכן שהתכוונו ל-GUI של wa-crypt-tools או ל-whapa-gui.
- מצב הרישיון של `cedroid/whatsapp-forensic-tool` — הריפו קיים (יש לו אתר תיעוד), אבל לא הצלחתי לקרוא קובץ LICENSE. לבדוק לפני כל שימוש, גם כייחוס.
- תאריך הקומיט האחרון של `whoozle/android-file-transfer-linux` — v4.5 אומת, אך לא נמצא תאריך מדויק. לבדוק בדף הריפו.

---

## 6. השלכות על מסמכים קיימים

1. `docs/WHATSAPP_ARCHIVE_SPEC.md` §5.1: להוסיף הערה (לא תיקון): הורדה אוטומטית מ-Drive (`wabdd`) אפשרית טכנית, לא בשירות.
2. `docs/WHATSAPP_ARCHIVE_SPEC.md` §9: להוסיף את KnugiHK כמנוע הייצוא הראשי ולהוריד את wa-crypt-tools ל-"אופציונלי, תהליך משנה". לתקן "64 ספרות" ← "64 תווים הקסדצימליים" בכל המסמך.
3. `pyproject.toml`: `layer2 = ["whatsapp-chat-exporter[vcards]"]` במקום `wa-crypt-tools`; לשקול הסרת `python-bidi` והוספת `uharfbuzz`; להוסיף `pyHanko`.
4. `ROADMAP.md` WP3: מניפסט בפורמט BagIt. WP5: pyHanko + text shaping. WP10: cage + autoinstall.
5. `docs/SECURITY.md` §1: מסלול TPM מומלץ = `tpm2-pkcs11` ← pyHanko (PKCS#11), בלי קוד TPM ייעודי.

7. **בוצע (2026-11-10):** ביטול העתקת SQL מ-msgstore-viewer; KnugiHK כמנוע WP11–12; "64 ספרות" ← "64 תווים הקסדצימליים"; WP13–15 (איחוד) נוספו ל-ROADMAP.
