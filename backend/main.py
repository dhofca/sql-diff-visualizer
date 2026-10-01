"""Local-only web app: upload two MySQL structure dumps, get a diff tree."""

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from .diff import diff_schemas
from .parser import parse_schema

MAX_FILE_BYTES = 50 * 1024 * 1024
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="SQL Schema Diff", docs_url=None, redoc_url=None, openapi_url=None)


async def _read_sql(upload: UploadFile) -> str:
    data = await upload.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, f"File {upload.filename} exceeds {MAX_FILE_BYTES // 1024 // 1024} MB")
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(400, f"Cannot decode file {upload.filename}")


@app.post("/api/diff")
async def diff(old: UploadFile = File(...), new: UploadFile = File(...)) -> dict:
    old_schema = parse_schema(await _read_sql(old))
    new_schema = parse_schema(await _read_sql(new))
    result = diff_schemas(old_schema, new_schema)
    result["files"] = {"old": old.filename, "new": new.filename}
    return result


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
