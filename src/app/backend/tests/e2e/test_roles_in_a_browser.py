"""
End-to-end tests: a real browser drives the real page against a running server, once for each role.

These need a running backend, so they are skipped unless you say where it is. In one terminal:

    cd src/app/backend
    uvicorn main:app --port 8000

In a second terminal (one-time install: pip install pytest playwright, then: playwright install chromium):

    set CERVIGRADE_E2E_URL=http://localhost:8000
    set CERVIGRADE_E2E_ADMIN_PASSWORD=<the admin password>
    python -m pytest tests/e2e -v

The tests create their own technician and clinician accounts, and deactivate them at the end.
Set CERVIGRADE_E2E_HEADED=1 to watch the browser work.
"""

import io
import os
import time
import uuid

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from PIL import Image                                                  # noqa: E402  (a dependency of the app)

URL = os.environ.get("CERVIGRADE_E2E_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("CERVIGRADE_E2E_ADMIN", "admin@alustudent.com")
ADMIN_PASSWORD = os.environ.get("CERVIGRADE_E2E_ADMIN_PASSWORD", "")
PASSWORD = "E2e-Passw0rd!1"
GRADING_TIMEOUT_MS = 10 * 60 * 1000       # a photo can take minutes on a laptop CPU

pytestmark = pytest.mark.skipif(not URL, reason="set CERVIGRADE_E2E_URL (and the admin password) with the server running")


def one_cell_png():
    """A 200 x 200 picture. Small photos are graded as one cell, so this finishes in seconds."""
    img = Image.effect_noise((200, 200), 60).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def playwright_instance():
    with sync_api.sync_playwright() as p:
        yield p


@pytest.fixture(scope="module")
def api(playwright_instance):
    ctx = playwright_instance.request.new_context(base_url=URL)
    yield ctx
    ctx.dispose()


@pytest.fixture(scope="module")
def accounts(api):
    """A technician and a clinician made for this run, with a slide uploaded by the technician."""
    login = api.post("/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert login.ok, "the admin could not sign in: check CERVIGRADE_E2E_ADMIN_PASSWORD"
    admin = {"Authorization": "Bearer " + login.json()["token"]}
    tag = uuid.uuid4().hex[:8]
    made = {}
    for role in ("technician", "clinician"):
        email = f"e2e.{role}.{tag}@alustudent.com"
        r = api.post("/users", headers=admin, data={"username": email, "full_name": f"E2E {role}", "role": role, "password": PASSWORD})
        assert r.status == 201, r.text()
        made[role] = {"email": email, "id": r.json()["id"]}
    tech = api.post("/auth/login", data={"username": made["technician"]["email"], "password": PASSWORD}).json()["token"]
    slide = api.post("/slides", headers={"Authorization": "Bearer " + tech}, timeout=GRADING_TIMEOUT_MS, multipart={
        "patient_code": f"E2E-{tag}", "files": {"name": "cell.png", "mimeType": "image/png", "buffer": one_cell_png()}})
    assert slide.status == 201, slide.text()
    made["slide_id"] = slide.json()["id"]
    yield made
    for role in ("technician", "clinician"):
        api.patch(f"/users/{made[role]['id']}", headers=admin, data={"active": False})


@pytest.fixture(scope="module")
def browser(playwright_instance):
    b = playwright_instance.chromium.launch(headless=not os.environ.get("CERVIGRADE_E2E_HEADED"))
    yield b
    b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    p = ctx.new_page()
    p.set_default_timeout(20000)
    yield p
    ctx.close()


def sign_in(page, email, password=PASSWORD):
    page.goto(f"{URL}/app#/login")
    page.wait_for_selector("#lu")
    page.fill("#lu", email)
    page.fill("#lp", password)
    page.click("button[type=submit]")


def test_an_outside_email_is_refused(page):
    sign_in(page, "someone@gmail.com", "whatever-1")
    page.wait_for_selector(".msg:not(:empty)")
    assert "@alustudent.com" in page.inner_text(".msg")


def test_a_wrong_password_is_refused(page, accounts):
    sign_in(page, accounts["technician"]["email"], "not-the-password")
    page.wait_for_selector(".msg:not(:empty)")
    assert "Wrong email or password" in page.inner_text(".msg")


def test_a_signed_out_visitor_is_sent_to_sign_in(page):
    page.goto(f"{URL}/app#/slides")
    page.wait_for_selector("#lu")
    assert "sign in to continue" in page.inner_text(".notice").lower()


def test_technician_lands_on_new_check_and_is_kept_out_of_admin_pages(page, accounts):
    sign_in(page, accounts["technician"]["email"])
    page.wait_for_url("**#/new")
    page.goto(f"{URL}/app#/users")
    page.wait_for_url("**#/new")


def test_technician_sees_the_result_but_cannot_review_it(page, accounts):
    sign_in(page, accounts["technician"]["email"])
    page.wait_for_url("**#/new")
    page.goto(f"{URL}/app#/slides/{accounts['slide_id']}")
    page.wait_for_selector(".verdict")
    assert "Waiting for a clinician" in page.inner_text(".cards")


def test_technician_can_upload_a_photo_through_the_page(page, accounts, tmp_path):
    photo = tmp_path / "cell.png"
    photo.write_bytes(one_cell_png())
    sign_in(page, accounts["technician"]["email"])
    page.wait_for_url("**#/new")
    page.fill("#pc", f"UI-{uuid.uuid4().hex[:6]}")
    page.set_input_files("#file", str(photo))
    page.click("#go")
    page.wait_for_selector(".working")                                    # the progress panel appears while grading
    page.wait_for_url("**#/slides/*", timeout=GRADING_TIMEOUT_MS)
    page.wait_for_selector(".verdict")


def test_a_patient_code_with_a_space_is_refused_before_uploading(page, accounts, tmp_path):
    photo = tmp_path / "cell.png"
    photo.write_bytes(one_cell_png())
    sign_in(page, accounts["technician"]["email"])
    page.wait_for_url("**#/new")
    page.fill("#pc", "Jane Doe")
    page.set_input_files("#file", str(photo))
    page.click("#go")
    assert "Never a name" in page.inner_text(".msg")


def test_clinician_can_confirm_correct_and_undo(page, accounts):
    sign_in(page, accounts["clinician"]["email"])
    page.wait_for_url("**#/slides")
    page.goto(f"{URL}/app#/slides/{accounts['slide_id']}")
    page.wait_for_selector(".review .pill.go")
    page.click(".review .pill.go")
    page.wait_for_selector("text=Confirmed")
    page.click("button:has-text('Undo')")
    page.wait_for_selector(".review select.pill")
    other = page.locator(".review select.pill option:not([value=''])").first.get_attribute("value")
    page.select_option(".review select.pill", other)
    page.wait_for_selector("text=Changed from")
    page.click("button:has-text('Undo')")
    page.wait_for_selector(".review .pill.go")


def test_clinician_is_kept_out_of_records(page, accounts):
    sign_in(page, accounts["clinician"]["email"])
    page.wait_for_url("**#/slides")
    page.goto(f"{URL}/app#/records")
    page.wait_for_url("**#/slides")


def test_admin_sees_records_and_the_agreement_card(page):
    sign_in(page, ADMIN_EMAIL, ADMIN_PASSWORD)
    page.wait_for_url("**#/records")
    page.wait_for_selector(".agree")
    assert "Clinician agreement" in page.inner_text(".agree")


def test_admin_can_add_an_institution_user_but_not_an_outsider(page):
    sign_in(page, ADMIN_EMAIL, ADMIN_PASSWORD)
    page.wait_for_url("**#/records")
    page.goto(f"{URL}/app#/users")
    page.wait_for_selector("#nu")
    page.fill("#nf", "Outside Person")
    page.fill("#nu", "outsider@yahoo.com")
    page.fill("#np", PASSWORD)
    page.click("button:has-text('Add user')")
    page.wait_for_selector("form .msg:not(:empty)")
    assert "@alustudent.com" in page.inner_text("form .msg")
    email = f"e2e.added.{uuid.uuid4().hex[:6]}@alustudent.com"
    page.fill("#nu", email)
    page.fill("#nf", "Added By Test")
    page.click("button:has-text('Add user')")
    page.wait_for_selector(f".urow:has-text('{email}')")
    row = page.locator(".urow", has_text=email)                          # clean up: delete it again (two clicks)
    row.locator("button:has-text('Delete')").click()
    row.locator("button.danger").click()
    page.wait_for_function("e => !document.body.innerText.includes(e)", arg=email)
