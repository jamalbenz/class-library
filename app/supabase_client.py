import os
from dotenv import load_dotenv
import httpx

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in .env")


def supabase_headers(access_token: str | None = None) -> dict:
    """
    Default headers for Supabase REST/Auth calls.
    - apikey always required
    - Authorization: Bearer <token> (user) OR Bearer <anon key> (anon)
    - Prefer: helps PostgREST return behavior
    """
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    headers["Authorization"] = f"Bearer {access_token or SUPABASE_ANON_KEY}"
    return headers


async def sb_post(path: str, json: dict | None = None, access_token: str | None = None):
    url = f"{SUPABASE_URL}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.post(url, headers=supabase_headers(access_token), json=json)


async def sb_get(path: str, access_token: str | None = None):
    url = f"{SUPABASE_URL}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.get(url, headers=supabase_headers(access_token))


async def sb_patch(path: str, json: dict | None = None, access_token: str | None = None):
    url = f"{SUPABASE_URL}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.patch(url, headers=supabase_headers(access_token), json=json)


async def sb_delete(path: str, access_token: str | None = None):
    url = f"{SUPABASE_URL}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.delete(url, headers=supabase_headers(access_token))


async def sb_upload_file(
    bucket: str,
    path: str,
    file_bytes: bytes,
    content_type: str,
    access_token: str | None = None,
):
    """
    Upload to Supabase Storage:
    POST /storage/v1/object/<bucket>/<path>

    Note:
    - Needs Authorization (user token) when bucket has RLS policies (admin upload)
    """
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {access_token or SUPABASE_ANON_KEY}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        return await client.post(url, headers=headers, content=file_bytes)


def storage_public_url(bucket: str, path: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"

