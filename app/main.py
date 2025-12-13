# app/main.py

import uuid
import mimetypes
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import set_session_cookie, clear_session_cookie, read_session_cookie
from app.supabase_client import (
    sb_post, sb_get, sb_patch, sb_delete,
    sb_upload_file, storage_public_url,
    SUPABASE_URL, SUPABASE_ANON_KEY,
)

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["SUPABASE_URL"] = SUPABASE_URL
templates.env.globals["SUPABASE_ANON_KEY"] = SUPABASE_ANON_KEY


def require_session(request: Request):
    return read_session_cookie(request)


# ===== ADMIN (simple by email) =====
ADMIN_EMAILS = {"benzjamal45@gmail.com"}  # بدّلها بإيميل الأدمن ديالك

async def is_admin(sess: dict) -> bool:
    return (sess.get("email") or "").lower() in {e.lower() for e in ADMIN_EMAILS}


# ✅ approval stored in user_profiles.is_approved
async def get_my_approval(sess: dict) -> bool:
    r = await sb_get(
        f"/rest/v1/user_profiles?select=is_approved&user_id=eq.{sess['user_id']}&limit=1",
        access_token=sess["access_token"],
    )
    if r.status_code >= 400 or not r.json():
        return False
    return bool(r.json()[0].get("is_approved"))


# =========================
# Home
# =========================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    sess = require_session(request)
    if sess:
        return RedirectResponse("/books?filter=all", status_code=303)
    return templates.TemplateResponse(
        "base.html",
        {"request": request, "title": "Home", "session": None, "message": "Welcome! Please login or signup."},
    )


# =========================
# Auth
# =========================
@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    sess = require_session(request)
    if sess:
        return RedirectResponse("/books?filter=all", status_code=303)
    return templates.TemplateResponse("signup.html", {"request": request, "title": "Signup", "session": None})


@app.post("/signup")
async def signup(full_name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    r = await sb_post("/auth/v1/signup", json={"email": email, "password": password, "data": {"full_name": full_name}})
    if r.status_code >= 400:
        return RedirectResponse("/signup?error=1", status_code=303)

    data = r.json()
    session = data.get("session")
    if not session:
        # needs email confirm
        return RedirectResponse("/login?confirm=1", status_code=303)

    resp = RedirectResponse("/books?filter=all", status_code=303)
    set_session_cookie(
        resp,
        session["access_token"],
        session["refresh_token"],
        session["user"]["id"],
        session["user"].get("email") or email,
    )

    # ✅ create profile (approved=false) - ignore errors if exists
    try:
        await sb_post(
            "/rest/v1/user_profiles",
            json={
                "user_id": session["user"]["id"],
                "email": session["user"].get("email") or email,
                "full_name": full_name,
                "is_approved": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            access_token=session["access_token"],
        )
    except Exception:
        pass

    return resp


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    sess = require_session(request)
    if sess:
        return RedirectResponse("/books?filter=all", status_code=303)

    message = None
    if request.query_params.get("confirm") == "1":
        message = "Account created. Check your email to confirm, then login."
    if request.query_params.get("error") == "1":
        message = "Login failed. Check email/password."

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "title": "Login", "session": None, "message": message},
    )


@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    r = await sb_post("/auth/v1/token?grant_type=password", json={"email": email, "password": password})
    if r.status_code >= 400:
        return RedirectResponse("/login?error=1", status_code=303)

    data = r.json()

    resp = RedirectResponse("/books?filter=all", status_code=303)
    set_session_cookie(
        resp,
        data["access_token"],
        data["refresh_token"],
        data["user"]["id"],
        data["user"].get("email") or email,
    )

    # ✅ ensure profile exists
    pr = await sb_get(
        f"/rest/v1/user_profiles?select=user_id&user_id=eq.{data['user']['id']}&limit=1",
        access_token=data["access_token"],
    )
    if pr.status_code < 400 and not pr.json():
        await sb_post(
            "/rest/v1/user_profiles",
            json={
                "user_id": data["user"]["id"],
                "email": data["user"].get("email") or email,
                "full_name": (data["user"].get("user_metadata") or {}).get("full_name") or "",
                "is_approved": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            access_token=data["access_token"],
        )

    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    clear_session_cookie(resp)
    return resp


# =========================
# Forgot / Reset Password
# =========================
@app.get("/forgot", response_class=HTMLResponse)
async def forgot_page(request: Request):
    sess = require_session(request)
    if sess:
        return RedirectResponse("/books?filter=all", status_code=303)

    msg = request.query_params.get("msg")
    message = None
    if msg == "sent":
        message = "✅ تفقد الإيميل ديالك (حتى Spam)."
    elif msg == "error":
        message = "❌ وقع مشكل. عاود جرّب."

    return templates.TemplateResponse(
        "forgot.html",
        {"request": request, "title": "Forgot Password", "session": None, "message": message},
    )


@app.post("/forgot")
async def forgot_send(request: Request, email: str = Form(...)):
    # local:  http://127.0.0.1:8000
    # online: https://class-library.onrender.com
    base = str(request.base_url).rstrip("/")
    redirect_url = f"{base}/reset"

    r = await sb_post(
        "/auth/v1/recover",
        json={"email": email, "redirect_to": redirect_url},
    )

    print("FORGOT REDIRECT:", redirect_url)
    print("FORGOT STATUS:", r.status_code)
    print("FORGOT BODY:", r.text)

    if r.status_code >= 400:
        return RedirectResponse("/forgot?msg=error", status_code=303)

    return RedirectResponse("/forgot?msg=sent", status_code=303)


@app.get("/reset", response_class=HTMLResponse)
async def reset_page(request: Request):
    return templates.TemplateResponse(
        "reset.html",
        {"request": request, "title": "Reset Password", "session": None},
    )


# =========================
# Books (list)
# =========================
@app.get("/books", response_class=HTMLResponse)
async def books_page(request: Request):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)

    approved = await get_my_approval(sess)

    # 1) books
    r = await sb_get(
        "/rest/v1/books_with_ratings?select=*&order=created_at.desc",
        access_token=sess["access_token"],
    )
    books = r.json() if r.status_code < 400 else []

    # 2) my ratings
    rr = await sb_get(
        f"/rest/v1/ratings?select=book_id,rating&user_id=eq.{sess['user_id']}",
        access_token=sess["access_token"],
    )
    rated_map = {}
    if rr.status_code < 400:
        for row in rr.json():
            rated_map[row["book_id"]] = row["rating"]

    # 3) my active borrows (via borrow_history view)
    br = await sb_get(
        f"/rest/v1/borrow_history?select=book_id,due_date,status&user_id=eq.{sess['user_id']}&status=eq.borrowed",
        access_token=sess["access_token"],
    )
    active_borrows = {}
    if br.status_code < 400:
        for row in br.json():
            active_borrows[row["book_id"]] = row.get("due_date")

    # 4) enrich per book
    for b in books:
        b["my_rating"] = rated_map.get(b["id"])

        due = active_borrows.get(b["id"])
        b["my_borrowed"] = b["id"] in active_borrows
        b["my_due_date"] = due

        total = int(b.get("copies_total") or 1)
        borrowed = int(b.get("copies_borrowed") or 0)
        b["available_copies"] = max(total - borrowed, 0)

    # 5) msg/search/filter
    q = (request.query_params.get("q") or "").strip().lower()
    filter_mode = (request.query_params.get("filter") or "all").strip().lower()
    msg = request.query_params.get("msg")

    message = None
    if msg == "no_copies_left":
        message = "⚠️ ما بقات حتى نسخة."
    elif msg == "borrowed":
        message = "✅ تسلفات نسخة."
    elif msg == "returned":
        message = "✅ ترجعات نسخة."
    elif msg == "borrow_error":
        message = "❌ وقع مشكل فـ Borrow."
    elif msg == "return_error":
        message = "❌ وقع مشكل فـ Return."
    elif msg == "not_your_book":
        message = "⚠️ ماشي أنت اللي مسلف هاد الكتاب."
    elif msg == "already_rated":
        message = "⚠️ راك قيّمتي هاد الكتاب من قبل."
    elif msg == "rated":
        message = "✅ شكراً! تسجّل التقييم ديالك."
    elif msg == "rate_error":
        message = "❌ وقع مشكل فالتقييم. عاود جرّب."
    elif msg == "not_admin":
        message = "⚠️ ماعندكش صلاحية Admin."
    elif msg == "await_approval":
        message = "⏳ خاص Admin يقبل الحساب ديالك باش تولّي تقدر تدير Borrow."

    if q:
        def match(book):
            hay = f"{book.get('title','')} {book.get('author','')} {book.get('code','')}".lower()
            return q in hay
        books = [b for b in books if match(b)]

    if filter_mode == "available":
        books = [b for b in books if b.get("available_copies", 0) > 0]
    elif filter_mode == "reserved":
        books = [b for b in books if b.get("available_copies", 0) == 0]
    elif filter_mode == "mine":
        books = [b for b in books if b.get("my_borrowed")]

    return templates.TemplateResponse(
        "books.html",
        {
            "request": request,
            "title": "Books",
            "session": sess,
            "books": books,
            "q": q,
            "filter": filter_mode,
            "message": message,
            "approved": approved,
        },
    )


# =========================
# Borrow / Return (RPC)
# =========================
@app.post("/borrow/{book_id}")
async def borrow_book(request: Request, book_id: int):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)

    approved = await get_my_approval(sess)
    if not approved:
        return RedirectResponse("/books?filter=all&msg=await_approval", status_code=303)

    r = await sb_post(
        "/rest/v1/rpc/borrow_copy",
        json={"p_book_id": book_id, "p_user_id": sess["user_id"]},
        access_token=sess["access_token"],
    )

    if r.status_code >= 400:
        txt = (r.text or "").lower()
        if "no_copies_left" in txt:
            return RedirectResponse("/books?filter=all&msg=no_copies_left", status_code=303)
        return RedirectResponse("/books?filter=all&msg=borrow_error", status_code=303)

    return RedirectResponse("/books?filter=all&msg=borrowed", status_code=303)


@app.post("/return/{book_id}")
async def return_book(request: Request, book_id: int):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)

    r = await sb_post(
        "/rest/v1/rpc/return_copy",
        json={"p_book_id": book_id, "p_user_id": sess["user_id"]},
        access_token=sess["access_token"],
    )

    if r.status_code >= 400:
        txt = (r.text or "").lower()
        if "not_your_book" in txt:
            return RedirectResponse("/books?filter=all&msg=not_your_book", status_code=303)
        return RedirectResponse("/books?filter=all&msg=return_error", status_code=303)

    return RedirectResponse("/books?filter=all&msg=returned", status_code=303)


# (optional safety) avoid GET calling borrow/return
@app.get("/borrow/{book_id}")
async def borrow_get(book_id: int):
    return RedirectResponse("/books?filter=all", status_code=303)

@app.get("/return/{book_id}")
async def return_get(book_id: int):
    return RedirectResponse("/books?filter=all", status_code=303)


# =========================
# History
# =========================
@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)

    r = await sb_get(
        f"/rest/v1/borrow_history?select=*&user_id=eq.{sess['user_id']}&order=borrowed_at.desc",
        access_token=sess["access_token"],
    )
    history = r.json() if r.status_code < 400 else []

    return templates.TemplateResponse(
        "history.html",
        {"request": request, "title": "My History", "session": sess, "history": history},
    )


# =========================
# Ratings
# =========================
@app.post("/rate/{book_id}")
async def rate_book(request: Request, book_id: int, rating: int = Form(...)):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)

    payload = {"book_id": book_id, "user_id": sess["user_id"], "rating": int(rating)}
    r = await sb_post("/rest/v1/ratings", json=payload, access_token=sess["access_token"])

    if r.status_code >= 400:
        txt = (r.text or "").lower()
        if "duplicate" in txt or "unique" in txt:
            return RedirectResponse("/books?msg=already_rated", status_code=303)
        return RedirectResponse("/books?msg=rate_error", status_code=303)

    return RedirectResponse("/books?msg=rated", status_code=303)


# =========================
# Admin - Add book page
# =========================
@app.get("/admin/books/new", response_class=HTMLResponse)
async def admin_add_book_page(request: Request):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    if not await is_admin(sess):
        return RedirectResponse("/books?filter=all&msg=not_admin", status_code=303)

    msg = request.query_params.get("msg")
    message = None
    if msg == "upload_error":
        message = "❌ Upload failed."
    elif msg == "created":
        message = "✅ Book added."

    return templates.TemplateResponse(
        "admin_add_book.html",
        {"request": request, "title": "Add Book", "session": sess, "message": message},
    )


# =========================
# Admin - Add book (upload)
# =========================
@app.post("/admin/books/new")
async def admin_add_book(
    request: Request,
    title: str = Form(...),
    author: str = Form(...),
    code: str = Form(...),
    description: str = Form(""),
    copies_total: int = Form(1),
    image: UploadFile = File(None),
):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    if not await is_admin(sess):
        return RedirectResponse("/books?filter=all&msg=not_admin", status_code=303)

    image_url = None

    if image and image.filename:
        ext = (image.filename.rsplit(".", 1)[-1] or "jpg").lower()
        file_path = f"{uuid.uuid4().hex}.{ext}"
        data = await image.read()

        guessed_type, _ = mimetypes.guess_type(image.filename)
        content_type = guessed_type or image.content_type or "image/jpeg"

        up = await sb_upload_file(
            "book-images",
            file_path,
            data,
            content_type,
            access_token=sess["access_token"],
        )

        if up.status_code >= 400:
            print("UPLOAD ERROR:", up.status_code, up.text)
            return RedirectResponse("/admin/books/new?msg=upload_error", status_code=303)

        image_url = storage_public_url("book-images", file_path)

    payload = {
        "title": title,
        "author": author,
        "code": code,
        "description": description,
        "image_url": image_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "copies_total": int(copies_total) if int(copies_total) > 0 else 1,
        "copies_borrowed": 0,
    }

    ir = await sb_post("/rest/v1/books", json=payload, access_token=sess["access_token"])
    if ir.status_code >= 400:
        print("INSERT BOOK ERROR:", ir.status_code, ir.text)
        return RedirectResponse("/admin/books/new?msg=upload_error", status_code=303)

    return RedirectResponse("/admin/books/new?msg=created", status_code=303)


# =========================
# Admin - List books
# =========================
@app.get("/admin/books", response_class=HTMLResponse)
async def admin_books(request: Request):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    if not await is_admin(sess):
        return RedirectResponse("/books?filter=all&msg=not_admin", status_code=303)

    r = await sb_get("/rest/v1/books?select=*&order=created_at.desc", access_token=sess["access_token"])
    books = r.json() if r.status_code < 400 else []

    msg = request.query_params.get("msg")
    message = None
    if msg == "deleted":
        message = "✅ Deleted."
    elif msg == "delete_error":
        message = "❌ Delete error."
    elif msg == "cant_delete_reserved":
        message = "⚠️ Can't delete (some copies borrowed)."
    elif msg == "updated":
        message = "✅ Updated."
    elif msg == "update_error":
        message = "❌ Update error."
    elif msg == "copies_too_low":
        message = "⚠️ copies_total ما يقدرش يكون أقل من copies_borrowed."

    return templates.TemplateResponse(
        "admin_books.html",
        {"request": request, "title": "Admin Books", "session": sess, "books": books, "message": message},
    )

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    if not await is_admin(sess):
        return RedirectResponse("/books?msg=not_admin", status_code=303)

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "title": "Admin Dashboard",
            "session": sess,
        },
    )

# =========================
# Admin - Update copies_total
# =========================
@app.post("/admin/books/{book_id}/copies")
async def admin_update_copies(request: Request, book_id: int, copies_total: int = Form(...)):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    if not await is_admin(sess):
        return RedirectResponse("/books?filter=all&msg=not_admin", status_code=303)

    br = await sb_get(
        f"/rest/v1/books?select=copies_borrowed&id=eq.{book_id}&limit=1",
        access_token=sess["access_token"],
    )
    if br.status_code >= 400 or not br.json():
        return RedirectResponse("/admin/books?msg=update_error", status_code=303)

    borrowed = int(br.json()[0].get("copies_borrowed") or 0)
    new_total = int(copies_total)

    if new_total < borrowed:
        return RedirectResponse("/admin/books?msg=copies_too_low", status_code=303)

    ur = await sb_patch(
        f"/rest/v1/books?id=eq.{book_id}",
        json={"copies_total": new_total},
        access_token=sess["access_token"],
    )
    if ur.status_code >= 400:
        return RedirectResponse("/admin/books?msg=update_error", status_code=303)

    return RedirectResponse("/admin/books?msg=updated", status_code=303)


# =========================
# Admin - Delete book
# =========================
@app.post("/admin/books/{book_id}/delete")
async def admin_delete_book(request: Request, book_id: int):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    if not await is_admin(sess):
        return RedirectResponse("/books?filter=all&msg=not_admin", status_code=303)

    br = await sb_get(
        f"/rest/v1/books?select=copies_borrowed&id=eq.{book_id}&limit=1",
        access_token=sess["access_token"],
    )
    if br.status_code >= 400 or not br.json():
        return RedirectResponse("/admin/books?msg=delete_error", status_code=303)

    if int(br.json()[0].get("copies_borrowed") or 0) > 0:
        return RedirectResponse("/admin/books?msg=cant_delete_reserved", status_code=303)

    dr = await sb_delete(f"/rest/v1/books?id=eq.{book_id}", access_token=sess["access_token"])
    if dr.status_code >= 400:
        return RedirectResponse("/admin/books?msg=delete_error", status_code=303)

    return RedirectResponse("/admin/books?msg=deleted", status_code=303)


# =========================
# Admin - Users approval
# =========================
@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    if not await is_admin(sess):
        return RedirectResponse("/books?filter=all&msg=not_admin", status_code=303)

    r = await sb_get(
        "/rest/v1/user_profiles?select=*&order=created_at.desc",
        access_token=sess["access_token"],
    )
    users = r.json() if r.status_code < 400 else []

    return templates.TemplateResponse(
        "admin_users.html",
        {"request": request, "title": "Users", "session": sess, "users": users},
    )


@app.post("/admin/users/{user_id}/approve")
async def admin_approve_user(request: Request, user_id: str):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    if not await is_admin(sess):
        return RedirectResponse("/books?filter=all&msg=not_admin", status_code=303)

    await sb_patch(
        f"/rest/v1/user_profiles?user_id=eq.{user_id}",
        json={"is_approved": True, "approved_at": datetime.now(timezone.utc).isoformat()},
        access_token=sess["access_token"],
    )
    return RedirectResponse("/admin/users", status_code=303)
@app.post("/admin/users/{user_id}/unapprove")
async def admin_unapprove_user(request: Request, user_id: str):
    sess = require_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    if not await is_admin(sess):
        return RedirectResponse("/books?filter=all&msg=not_admin", status_code=303)

    await sb_patch(
        f"/rest/v1/user_profiles?user_id=eq.{user_id}",
        json={"is_approved": False, "approved_at": None},
        access_token=sess["access_token"],
    )
    return RedirectResponse("/admin/users", status_code=303)


# =========================
# FAQ / About
# =========================
@app.get("/faq", response_class=HTMLResponse)
async def faq_page(request: Request):
    sess = require_session(request)
    return templates.TemplateResponse("faq.html", {"request": request, "title": "FAQ", "session": sess})


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    sess = require_session(request)
    return templates.TemplateResponse("about.html", {"request": request, "title": "About", "session": sess})


# =========================
# Health (UpTimeRobot)
# =========================
@app.get("/healthz", response_class=PlainTextResponse)
@app.head("/healthz")
async def healthz():
    return "ok"


# =========================
# Debug
# =========================
@app.get("/debug/books", response_class=PlainTextResponse)
async def debug_books(request: Request):
    sess = require_session(request)
    if not sess:
        return "NO SESSION (login first)"
    r = await sb_get("/rest/v1/books?select=*", access_token=sess["access_token"])
    return f"status={r.status_code}\nbody={r.text[:1500]}"


@app.get("/debug/last-book", response_class=PlainTextResponse)
async def debug_last_book(request: Request):
    sess = require_session(request)
    if not sess:
        return "NO SESSION"
    r = await sb_get(
        "/rest/v1/books?select=id,title,image_url&order=created_at.desc&limit=1",
        access_token=sess["access_token"],
    )
    return f"status={r.status_code}\n{r.text}"
