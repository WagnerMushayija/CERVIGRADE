"""
CerviGrade API.

Run with (from src/app/backend):
    uvicorn main:app --reload --port 8000

Then open:
    http://localhost:8000/app    (the web page)
    http://localhost:8000/docs   (Swagger UI: press Authorize after signing in through /auth/login)

Three kinds of user, as in the proposal's use case diagram:
  technician  registers a patient's slide (a pseudonym code) and uploads its images
  clinician   reviews each grade: confirms or corrects it
  admin       the data scientist: manages users, patients and slides, and sees the model status

Folders:
  core/          settings, sign-in security and the institution email rule
  db/            the SQLite connection and tables
  repositories/  the queries that read and write users and slide records
  services/      grading vocabulary, the cell detector, the classifier, the pipeline that joins them, Grad-CAM
  schemas/       what each request must contain
  routers/       the API endpoints, one file per topic

Images are stored in app_data/uploads on this computer and are removed when a slide is deleted.
Research prototype, not a medical device.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import ALLOWED_ORIGINS, FRONTEND_FILE
from db import database as db
from routers import auth, patients, predictions, slides, stats, status, users

db.init_db()
db.adopt_institution_emails()
db.bootstrap_admin()

app = FastAPI(
    title="CerviGrade API",
    description=("Severity grading for cervical cytology cell images, with sign-in, roles and saved records. "
                 "Each image gets a Bethesda grade and one of three groups (negative, low-grade, high-grade). "
                 "A slide's overall result is its most serious finding, using the clinician's confirmed grade where there is one. "
                 "Research prototype, not a medical device."),
    version="0.5.0",
)

# The page is served by this same server, so no other website needs access by default. To let a separate front end
# call the API, list its address(es) in CERVIGRADE_ORIGINS, comma separated (for example https://cervigrade.example.com).
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The page's own stylesheet and scripts (css/ and js/ next to index.html), served at /css and /js so the page can load them.
for _folder in ("css", "js"):
    _path = os.path.join(os.path.dirname(FRONTEND_FILE), _folder)
    if os.path.isdir(_path):
        app.mount(f"/{_folder}", StaticFiles(directory=_path), name=_folder)

for _router in (status.router, auth.router, users.router, stats.router, patients.router, slides.router, predictions.router):
    app.include_router(_router)
