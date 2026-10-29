# How CerviGrade works: the cheat sheet

Read this before any meeting. It answers: where does the backend run from, what database is it, where is the data, how do I look at the tables, and what happens when someone uploads a photo.

## 1. The big picture

CerviGrade is two programs that talk to each other over HTTP:

- **The backend** (`src/app/backend/`) is a Python program built with FastAPI. It does everything that matters: sign-in, saving records, running the detector and the CNN, making the Grad-CAM pictures.
- **The frontend** (`src/app/frontend/index.html`) is one web page with its own JavaScript. It only draws screens and calls the backend. The backend also hands the page out, at `/app`.

Both run **on your own laptop**. Nothing is hosted online unless you share it with a tunnel. When the page says "images are kept on the computer running the server", that computer is your laptop.

You start it with:

    cd src\app\backend
    uvicorn main:app --port 8000

`uvicorn` is the web server. `main:app` means "the object called `app` inside `main.py`". The address is `http://localhost:8000`. `localhost` means "this computer".

Useful addresses once it runs:

| Address | What you get |
|---|---|
| `/` or `/app` | The web page |
| `/docs` | Swagger: a list of every backend endpoint, where you can try them |
| `/health` | A quick "is it alive" check, plus which models are loaded |

## 2. Where everything lives

| What | Where |
|---|---|
| Backend code | `src/app/backend/*.py` |
| Web page | `src/app/frontend/index.html` |
| Model files | `models/` (`efficientnetb0_cric_retrained.keras` is the CNN, `stage2_severity_oversampled_best.pt` is the YOLO detector). They are not on GitHub, because `.gitignore` excludes them. |
| **Database and uploaded photos** | **`app_data/` in the repo root** (not on GitHub either) |

Inside `app_data/`:

- `cervigrade.db`: the database (one file).
- `uploads/<slide id>/`: the uploaded photos, one folder per slide.
- `secret.key`: the key that signs login tokens. Never share it.

Delete `app_data/` and the app starts empty, with a new admin account. Set the environment variable `CERVIGRADE_DATA` to keep the data somewhere else.

## 3. What each backend file does

| File | Job |
|---|---|
| `main.py` | The front door. Defines every endpoint (sign-in, users, slides, Grad-CAM, feedback, stats) and who is allowed to call it. |
| `institution.py` | The email rule: only `@alustudent.com` addresses. |
| `security.py` | Password hashing (PBKDF2 with a random salt, so passwords are never stored) and login tokens (JWT, valid 8 hours). |
| `db.py` | Opens the database, creates the tables, adds the first admin. |
| `records.py` | Builds the answers the page shows (a slide with its images, grades and reviews). |
| `pipeline.py` | The grading steps for a field photo: detector, crops, CNN, the "sure" rule, the verdict. |
| `model.py` | Loads the CNN, grades crops, computes Grad-CAM heat. |
| `gradcam.py` | Paints the heat as a coloured overlay. |
| `manage.py` | Admin commands from the terminal: `list-users`, `create-user`, `reset-password`, `seed-demo`. |
| `tests/` | Automated tests (`python -m pytest tests -q`). |

## 4. The database

**Type:** SQLite. It is a real relational (SQL) database that lives in a single file, so there is no server to install. Python includes it (`sqlite3`).

**Why not PostgreSQL?** The proposal (section 3.9) names PostgreSQL. For a laptop prototype SQLite is simpler, and the tables follow the same entity-relationship diagram, so they can move to PostgreSQL later. State this as a known difference from the proposal. It is not a mistake.

**The six tables:**

| Table | Holds | Linked to |
|---|---|---|
| `users` | Email (`username` column), full name, role, password hash, active, last login | |
| `patients` | A pseudonym code (never a name) | `created_by` is a user |
| `slides` | One upload session for a patient, plus a note | `patient_id`, `uploaded_by` |
| `slide_images` | Each photo in a slide: file name, where it is stored | `slide_id` |
| `predictions` | The result for one photo: grade, confidence, tier, probabilities, mode (`field` / `cell` / `whole`), and the box data as JSON | `slide_image_id` (one prediction per image) |
| `feedback_entries` | A clinician's answer: confirmed or corrected (and the corrected grade) | `prediction_id`, `clinician_id` |

The chain to remember: **patient, then slide, then image, then prediction, then feedback.** A user uploads slides and a clinician writes feedback.

Roles: **technician** uploads and sees their own work, **clinician** reviews and confirms or corrects, **admin** manages users and sees the agreement stats.

## 5. How to look at the tables

**Option A, easiest: DB Browser for SQLite** (free, from sqlitebrowser.org).

1. Install it and open it.
2. File, Open Database, then pick `app_data\cervigrade.db`.
3. **Database Structure** shows the tables. **Browse Data** shows the rows. **Execute SQL** lets you run queries.
4. Tip: close it, or use read-only, before running the server. Two programs writing at once can lock the file.

**Option B, no install: one line in PowerShell** (the path is the repo folder):

    python -c "import sqlite3;c=sqlite3.connect(r'app_data/cervigrade.db');print(c.execute('select id,username,role,active from users').fetchall())"

**Option C: from the page.** Sign in as admin, open Users and Records. The page shows users, slides and the agreement figure without any SQL.

**Option D: Swagger** at `/docs` lists every endpoint. Try `POST /auth/login`, copy the token it returns, click Authorize at the top and paste it, and you can call the other endpoints. It shows what the backend sends the page, not the raw tables.

**Queries worth knowing** (paste into Execute SQL):

All accounts:

    SELECT id, username, role, active, last_login FROM users;

Every photo with its grade and what the clinician said:

    SELECT s.id AS slide, p.code AS patient, si.filename, pr.predicted_class,
           ROUND(pr.confidence, 2) AS conf, pr.mode, f.action, f.corrected_class
    FROM slides s
    JOIN patients p ON p.id = s.patient_id
    JOIN slide_images si ON si.slide_id = s.id
    JOIN predictions pr ON pr.slide_image_id = si.id
    LEFT JOIN feedback_entries f ON f.prediction_id = pr.id
    ORDER BY s.id DESC;

How often clinicians agreed with the model:

    SELECT action, COUNT(*) FROM feedback_entries GROUP BY action;

Row counts per table:

    SELECT 'users', COUNT(*) FROM users UNION ALL SELECT 'patients', COUNT(*) FROM patients
    UNION ALL SELECT 'slides', COUNT(*) FROM slides UNION ALL SELECT 'images', COUNT(*) FROM slide_images
    UNION ALL SELECT 'predictions', COUNT(*) FROM predictions UNION ALL SELECT 'feedback', COUNT(*) FROM feedback_entries;

## 6. What happens when a technician uploads a photo

1. The page sends the photos to `POST /slides` with the login token in the request header.
2. `main.py` checks the token and the role, saves each file into `app_data/uploads/<slide id>/`, and creates rows in `patients`, `slides` and `slide_images`.
3. For each photo `pipeline.py` runs:
   - The **YOLO11n detector** slides a 224-pixel window over the photo and boxes every cell it finds. Overlapping boxes are merged.
   - Each box is cut out as a 200 by 200 crop.
   - The **EfficientNetB0 CNN** grades every crop.
   - A cell counts if it is Negative, or if the CNN is at least 90% sure. Unsure cells are set aside.
   - The photo's result is the most serious grade among the counted cells. A photo is flagged "worth a closer look" if a set-aside cell is worse.
4. The result is saved in `predictions` (with the boxes as JSON), and the page draws it.
5. A clinician opens the slide, confirms or corrects each grade, and that is saved in `feedback_entries`.
6. "Show where the model looked" calls `GET /predictions/{id}/cam`, which computes Grad-CAM on that cell when asked.

Small photos (400 pixels or less on both sides) skip the detector and are graded as one cell. If the detector file is missing, a big photo is graded whole and flagged unreliable.

## 7. Questions you may be asked

- **Is it hosted?** Not permanently. It runs on a laptop. Hosting needs a machine with about 2 GB of free memory, because TensorFlow and PyTorch are heavy.
- **Where is patient data?** In `app_data/` on that laptop. Patients are pseudonym codes, never names.
- **Who can get in?** Only `@alustudent.com` addresses, and only accounts an admin has created. There is no public sign-up.
- **Is the database secure?** Passwords are hashed with a salt. The file itself is not encrypted, so it should stay on a trusted machine.
- **Is it a medical device?** No. It is a research prototype that suggests a grade. A clinician confirms or corrects it.
- **How is it different from the proposal?** SQLite instead of PostgreSQL, a plain HTML/JavaScript page instead of React, one backend instead of separate preprocessing and inference services, and a YOLO detector plus CNN instead of the sliding-window design (the supervisor asked for the detector).
