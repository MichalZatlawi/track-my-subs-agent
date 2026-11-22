# Track My Subs — סוכן בינה מלאכותית לניהול מנויים (אבן דרך 1)

**מגישות:** עופרי כהן, מיכל זטלאוי  
**קורס:** סוכני AI (75973) — שנה״ל תשפ״ז, סמסטר א׳ | החוג למערכות מידע, האקדמית עמק יזרעאל  
**מרצה:** מר סאלח אבו שאהין  
**מועד הגשה:** 02.12.2026  

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/YOUR_USERNAME/track-my-subs-agent/blob/main/track_my_subs_milestone1.ipynb)

> **שימו לב לפני הגשה:** החליפו את `YOUR_USERNAME` בקישור ה-Open in Colab למעלה ובמשתנה `REPO_URL` במחברת בשם המשתמש שלכן ב-GitHub.

---

## סקירה כללית

מאגר זה מכיל את המימוש המלא של **אבן דרך 1** עבור סוכן ניהול המנויים **Track My Subs**:
* **5 כלים מוגדרי-חוזה** (`src/tools.py`) עם אימות קלט מלא ב-Pydantic (`extra="forbid"`), בדיקת הרשאות ואישור אנושי בקוד, הזרקת `user_id` מהסשן בלבד, תוצאות JSON מובנות, הבחנה בין כשל זמני לקבוע, מגבלת זמן (Timeout) וניסיונות חוזרים (עד 2 ניסיונות חוזרים עם Exponential Backoff לכלים אידמפוטנטיים בלבד).
* **ניהול מצב, זיכרון והקשר** (`src/state.py`) עם סכמת מצב מפורשת (`AgentState`), עדכונים בלתי-משתנים (`apply_event`), בידוד מוחלט בין שיחות (`thread_id`) ובין משתמשים (`user_id`), וניסוי השוואה אמפירי המריץ את אותה שאלה על הקשר מלא מול הקשר מצומצם.
* **לולאת סוכן עם תנאי עצירה ועקבות** (`src/agent.py`) עם תקציב מרבי של 7 צעדים (`MAX_STEPS=7`), מודל החלטה מדומה (`MockDecisionModel`) כברירת מחדל להרצה נקייה ללא מפתח API, מתאם אמיתי למודל Gemini (`GeminiDecisionModel`) כשמוגדר `GEMINI_API_KEY` ב-Colab Secrets, ושני קבצי עקבות ביצוע אמיתיים ב-`docs/traces/`.
* **33 בדיקות אוטומטיות** (`tests/`) הרצות בפקודה אחת (`pytest`) ללא תלות בשירות חיצוני.

---

## מבנה המאגר

```text
track-my-subs-agent/
├── README.md                          # הוראות התקנה, הרצה וקישור Open in Colab
├── requirements.txt                   # תלויות עם גרסאות מדויקות
├── track_my_subs_milestone1.ipynb     # מחברת Google Colab להרצה מקצה לקצה
├── data/
│   ├── sample_transactions.csv        # נתוני עסקאות סינתטיים (דמה בלבד)
│   ├── injection_transactions.csv     # קובץ סינתטי לבדיקת Prompt Injection
│   └── alternatives_catalog.json      # קטלוג חלופות מקומי סינתטי
├── src/
│   ├── tools.py                       # 5 הכלים, חוזים, אימות, הרשאות, timeout ו-retries
│   ├── state.py                       # סכמת מצב, בידוד שיחות, זיכרון והשוואת הקשר
│   └── agent.py                       # לולאת הסוכן, Mock/Gemini adapters ושמירת עקבות
├── tests/
│   ├── test_tools.py                  # 20 בדיקות כלים (תקין, שגוי, זמני, timeout, הרשאות)
│   ├── test_state.py                  # 6 בדיקות מצב, בידוד שיחות והשוואת הקשר
│   └── test_agent.py                  # 7 בדיקות אינטגרציה ללולאת הסוכן
└── docs/
    ├── milestone1.md                  # מסמך התיעוד המקיף של אבן דרך 1
    ├── ai_usage.md                    # נספח שימוש ב-AI
    └── traces/
        ├── trace_normal_run.json      # עקבת הרצה תקינה
        └── trace_transient_failure.json # עקבת הרצה עם כשל זמני והתאוששות
```

---

## הוראות התקנה והרצה מקומית (או ב-Google Colab)

### 1. שכפול והתקנת תלויות
```bash
git clone https://github.com/YOUR_USERNAME/track-my-subs-agent.git
cd track-my-subs-agent
pip install -r requirements.txt
```

### 2. הרצת כלל הבדיקות בפקודה אחת (ללא מפתח API וללא שירות חיצוני)
```bash
pytest -v
```
תוצאה צפויה: **33 passed**.

### 3. הרצת הדגמת השוואת ההקשר (היסטוריה מלאה מול מצומצמת)
```bash
python -c "from src.state import run_context_comparison; import json; print(json.dumps(run_context_comparison(), ensure_ascii=False, indent=2))"
```

---

## אבטחת מידע ופרטיות
* מאגר זה אינו מכיל מפתחות API, סיסמאות או מידע אישי אמיתי.
* כלל הנתונים בתיקיית `data/` הם נתונים סינתטיים שנוצרו לצורכי הדגמה ובדיקה בלבד.
* להפעלה עם מודל Gemini אמיתי ב-Google Colab, יש להגדיר מפתח ב-**Colab Secrets** תחת השם `GEMINI_API_KEY`.
