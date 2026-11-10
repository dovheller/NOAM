# פורמט הדוח החתום

## מזהה
`NOAM-<תיק>-R<גרסה>.pdf` — למשל `NOAM-2026-0418-R1.pdf`

## תוכן הדוח
1. **כותרת** — לוגו, שם העמדה, כתובת, מזהה דוח.
2. **פרטי סשן** — תיק, שם הלקוח, תאריך, שעות התחלה וסיום, מפעיל, עמדה, שירות.
3. **מכשיר מקור** — דגם, מזהה, ממשק (MTP).
4. **יעד** — סוג, נפח, מערכת קבצים.
5. **סיכום מספרי** — במקור, הועתקו, אומתו, דולגו, נפח, משך.
6. **פירוט לפי קטגוריה.**
7. **דילוגים ושגיאות** — אינדקס, סוג, קוד שגיאה. בלי שם קובץ.
8. **הסכמה** — חותמת זמן וחתימת הלקוח.
9. **טביעת המניפסט** — SHA-256.
10. **חתימה דיגיטלית** — ECDSA P-256, טביעת המפתח הציבורי.

## המניפסט (`manifest-<תיק>.json`)
```json
{
  "case": "2026-0418",
  "created": "2026-09-28T10:03:10+03:00",
  "files": [
    { "idx": 1, "group": "g01", "size": 2483021, "sha256": "…", "status": "verified" }
  ],
  "skipped": [ { "idx": 1842, "error": "ERR_READ_TIMEOUT" } ]
}
```
שמות הקבצים נשמרים בקובץ נפרד, `client-files-<תיק>.json` (idx → נתיב), שנשאר רק על מדיית היעד של הלקוח ולא נכנס לעמדה או לדוח. הוא מכיל את ה-SHA-256 של המניפסט, כך שאפשר להצליב ביניהם.

## חתימה
1. **PAdES בתוך ה-PDF** (pyHanko), בתעודה בחתימה עצמית של העמדה (`station.crt`). Adobe מציג "לא שונה מאז החתימה"; הזהות תוצג "לא מאומתת" עד שמישהו יסמוך על התעודה.
2. **חתימה מנותקת** `<דוח>.pdf.sig` (ECDSA P-256, DER) על הקובץ הסופי: `openssl dgst -sha256 -verify station.pub.pem -signature X.pdf.sig X.pdf`.

## BagIt (על מדיית הלקוח)
`<תיק>/` הוא תיק BagIt (RFC 8493): `bagit.txt`, `bag-info.txt` (כולל `NOAM-Manifest-SHA256`), `manifest-sha256.txt`, `tagmanifest-sha256.txt`, והקבצים תחת `data/`. אימות בלי התוכנה שלנו: `bagit.py --validate <תיק>`.

## קבצי מצב על היעד (`.noam/`)
| קובץ | תוכן |
|---|---|
| `progress.jsonl` | יומן התקדמות: שורה לכל קובץ שאומת (idx, נתיב, גודל, טביעה). מאפשר המשך אחרי ניתוק בלי העתקה כפולה. |
| `manifest-<תיק>.json` | המניפסט, בלי שמות. |
| `client-files-<תיק>.json` | רשימת השמות ללקוח. |
| `consent-<תיק>.png` | חתימת הלקוח (הטביעה שלה ביומן ובדוח). |
| `NOAM-<תיק>-R<n>.pdf` + `.sig` | עותק הדוח ללקוח. |

## קודי דילוג
| קוד | משמעות |
|---|---|
| `ERR_READ_FAILED` | המכשיר לא החזיר את הקובץ |
| `ERR_SIZE_MISMATCH` | נקרא גודל שונה ממה שהמכשיר דיווח |
| `ERR_VERIFY_MISMATCH` | הטביעה ביעד לא תאמה למקור, גם בניסיון שני |

## קודי מכשיר לא נגיש
`ERR_ADB_UNAUTHORIZED`, `ERR_USB_PERMISSION`, `ERR_NO_STORAGE_VISIBLE`, `ERR_ADB`.

## קודי עצירה (הסשן עובר ל"בוטל")
`ERR_DEVICE_DISCONNECTED`, `ERR_TARGET_SPACE`, `ERR_TARGET_WRITE`, `ERR_TARGET_READ`, `ERR_TARGET_COMMIT`, `ERR_TARGET_WRITE_TEST`, `ERR_TARGET_UNAVAILABLE`, `ERR_INDEX_FAILED`, `ERR_COPY_FAILED`, `ERR_OPERATOR_CANCELLED`.
