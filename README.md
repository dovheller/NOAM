# NOAM

עמדת גיבוי, העברה ושחזור נתונים, עם פרטיות כעיקרון: המפעיל רואה רק ספירות וסטטוס, הלקוח חותם על הסכמה, ובסוף הסשן מופק דוח חתום.

## מבנה

| נתיב | תוכן |
|---|---|
| `mockup/NOAM Mockup.dc.html` | המוקאפ הקליקבילי (מקור): קונסולת המפעיל, מסך נועם, ממשק הלקוח, ארכיון WhatsApp (שכבה 2) |
| `mockup/NOAM Mockup (standalone).html` | גרסה ארוזה בקובץ אחד עם כל ארבע הלשוניות — נפתחת בכל דפדפן, גם בלי אינטרנט (רק הגופן דורש רשת) |
| `mockup/noam-standalone-src.dc.html` | המקור של הגרסה הארוזה |
| `mockup/support.js`, `mockup/assets/` | ה-runtime והתמונות של המוקאפ |
| `ROADMAP.md` | **חלוקת העבודה למתכנת — 13 חבילות עבודה, לפי סדר** |
| `CLAUDE.md` | כללי עבודה ולקחים שכבר נלמדו |
| `docs/adr/` | החלטות מבניות (ממשק, מערכת הפעלה, רשת) |
| `docs/SECURITY.md` | מפתח חתימה, זהות, זמן, בידוד, שמירה |
| `docs/` | ארכיטקטורה, מודל פרטיות, אפיון שכבה 1, פורמט הדוח, טפסי הסכמה |
| `src/noam/` | שלד הקוד של הקיוסק (שכבה 1) |
| `src/noam_l2/` | שלד הקוד של ארכיון WhatsApp (שכבה 2) |
| `tests/` | בדיקות (ממתינות למימוש) |
| `docs/CONSOLIDATION_SPEC.md` | איחוד כמה מכשירים ומקורות לתיקייה אחת (WP13–15) |
| `docs/REPO_CANDIDATES.md` | ספריות וכלים פתוחים שנבדקו: מה לוקחים, מה לא, ולמה |
| `docs/WHATSAPP_ARCHIVE_SPEC.md` | אפיון שחזור ארכיון WhatsApp, שכבה 2 (גרסה מתוקנת) |

קובצי `.dc.html` הם פורמט של Claude Design ונטענים דרך `support.js`.

## הדגמה בלי חומרה

```bash
pip install -e ".[dev]"
python scripts/demo_station.py      # http://127.0.0.1:8000/operator  ·  /client
```

## התקנה בעמדה

`docs/INSTALL.md` (מקים) · `docs/OPERATOR_GUIDE.md` (נועם).

## התחלה

```bash
pip install -e ".[dev]"
pre-commit install
pytest
```

מתחילים מ-WP0 ב-`ROADMAP.md`.
