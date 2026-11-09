# NOAM

עמדת גיבוי, העברה ושחזור נתונים, עם פרטיות כעיקרון: המפעיל רואה רק ספירות וסטטוס, הלקוח חותם על הסכמה, ובסוף הסשן מופק דוח חתום.

## מבנה

| נתיב | תוכן |
|---|---|
| `mockup/NOAM Mockup.dc.html` | המוקאפ הקליקבילי (מקור): קונסולת המפעיל, מסך נועם, ממשק הלקוח, ארכיון WhatsApp (שכבה 2) |
| `mockup/NOAM Mockup (standalone).html` | גרסה ארוזה בקובץ אחד, נפתחת ישירות בדפדפן (בלי לשונית WhatsApp) |
| `mockup/noam-standalone-src.dc.html` | המקור של הגרסה הארוזה |
| `mockup/support.js`, `mockup/assets/` | ה-runtime והתמונות של המוקאפ |
| `docs/WHATSAPP_ARCHIVE_SPEC.md` | אפיון שחזור ארכיון WhatsApp, שכבה 2 (גרסה מתוקנת) |

קובצי `.dc.html` הם פורמט של Claude Design ונטענים דרך `support.js`.
