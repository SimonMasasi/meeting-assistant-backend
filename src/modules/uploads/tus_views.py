"""Resumable uploads over the tus 1.0.0 protocol (https://tus.io/protocols/resumable-upload).

Exists because meeting audio can reach 2 GB, which the single-request multipart
endpoint cannot carry: it buffers the whole body in memory and loses everything
when the connection drops. Here the client creates an upload, sends it in chunks,
and can resume from the server-reported offset after a failure.

Supported extensions: creation, termination, expiration.

Bytes are appended to a scratch file under SETTINGS.TUS_UPLOAD_DIR and only
streamed into the storage provider once the declared length has arrived, so
memory stays flat regardless of file size.
"""
import base64
import contextlib
import logging
import os
from datetime import datetime, timedelta

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from config import SETTINGS
from src.modules.auth.models import User
from src.shared.database import engine
from src.shared.dependencies import get_current_user
from src.utils.generators import Generator
from .models import TusUpload
from .services import UploadService

logger = logging.getLogger(__name__)

tus_router = APIRouter(prefix="/uploads/tus", tags=["uploads"])
upload_service = UploadService()

TUS_VERSION = "1.0.0"
TUS_EXTENSIONS = "creation,termination,expiration"
# Headers the browser must be able to read for resume to work at all.
TUS_EXPOSED_HEADERS = [
    "Location",
    "Upload-Offset",
    "Upload-Length",
    "Upload-Expires",
    "Tus-Resumable",
    "Tus-Version",
    "Tus-Max-Size",
    "Tus-Extension",
]
_WRITE_CHUNK_BYTES = 1024 * 1024


def _base_headers() -> dict[str, str]:
    return {"Tus-Resumable": TUS_VERSION, "Cache-Control": "no-store"}


def _require_tus_version(request: Request) -> None:
    """Every request except OPTIONS must carry a Tus-Resumable we support."""
    version = request.headers.get("Tus-Resumable")
    if version is None:
        raise HTTPException(status_code=412, detail="Missing Tus-Resumable header")
    if version != TUS_VERSION:
        raise HTTPException(status_code=412, detail=f"Unsupported tus version {version}")


def _parse_upload_metadata(raw: str | None) -> dict[str, str]:
    """Decode the tus Upload-Metadata header: comma-separated `key b64value`
    pairs, where a key may appear on its own to mean an empty value."""
    metadata: dict[str, str] = {}
    if not raw:
        return metadata
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split(" ", 1)
        key = parts[0]
        if len(parts) == 1:
            metadata[key] = ""
            continue
        try:
            metadata[key] = base64.b64decode(parts[1]).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"Malformed Upload-Metadata value for '{key}'")
    return metadata


def _buffer_dir() -> str:
    directory = os.path.realpath(os.path.abspath(SETTINGS.TUS_UPLOAD_DIR))
    os.makedirs(directory, exist_ok=True)
    return directory


def _safe_buffer_path(temp_path: str) -> str:
    """Confine a stored buffer path to TUS_UPLOAD_DIR.

    The path always comes from our own DB row rather than the client, but this
    keeps a corrupted or tampered row from reaching arbitrary files, mirroring
    LocalUploads._resolve_safe_path.
    """
    root = _buffer_dir()
    candidate = os.path.realpath(os.path.abspath(temp_path))
    if os.path.commonpath([root, candidate]) != root:
        raise HTTPException(status_code=500, detail="Invalid upload buffer path")
    return candidate


def _load_upload(upload_key: str, current_user: User) -> TusUpload:
    with Session(engine) as session:
        upload = session.exec(select(TusUpload).where(TusUpload.upload_key == upload_key)).first()

    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Upload belongs to another user")
    if upload.uploaded_file_id is not None:
        raise HTTPException(status_code=410, detail="Upload already completed")
    if upload.expires_at < datetime.now():
        raise HTTPException(status_code=410, detail="Upload expired")
    return upload


@tus_router.options("")
def tus_options() -> Response:
    """Advertise protocol support. Deliberately unauthenticated: it carries no
    upload data and clients probe it before attaching credentials."""
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            **_base_headers(),
            "Tus-Version": TUS_VERSION,
            "Tus-Extension": TUS_EXTENSIONS,
            "Tus-Max-Size": str(SETTINGS.TUS_MAX_UPLOAD_SIZE_BYTES),
        },
    )


@tus_router.post("", status_code=status.HTTP_201_CREATED)
def create_upload(request: Request, current_user: User = Depends(get_current_user)) -> Response:
    """Create an upload and return its Location. `Upload-Length` is required —
    the deferred-length extension is not supported."""
    _require_tus_version(request)

    raw_length = request.headers.get("Upload-Length")
    if raw_length is None:
        raise HTTPException(status_code=400, detail="Upload-Length header is required")
    try:
        total_size = int(raw_length)
    except ValueError:
        raise HTTPException(status_code=400, detail="Upload-Length must be an integer")
    if total_size < 0:
        raise HTTPException(status_code=400, detail="Upload-Length must not be negative")
    if total_size > SETTINGS.TUS_MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds the maximum size of {SETTINGS.TUS_MAX_UPLOAD_SIZE_BYTES} bytes",
        )

    metadata = _parse_upload_metadata(request.headers.get("Upload-Metadata"))
    filename = metadata.get("filename") or metadata.get("name")
    if not filename:
        raise HTTPException(status_code=400, detail="Upload-Metadata must include a filename")
    # Never let a client-supplied name escape the buffer directory or the
    # eventual stored object name.
    filename = os.path.basename(filename)
    if not filename or filename in (".", ".."):
        raise HTTPException(status_code=400, detail="Upload-Metadata filename is invalid")

    upload_key = Generator.generate_auth_token()
    temp_path = os.path.join(_buffer_dir(), f"{upload_key}.part")
    # Create the buffer up front so PATCH only ever opens an existing file.
    with open(temp_path, 'wb'):
        pass

    expires_at = datetime.now() + timedelta(seconds=SETTINGS.TUS_UPLOAD_EXPIRY_SECONDS)
    upload = TusUpload(
        upload_key=upload_key,
        filename=filename,
        content_type=metadata.get("filetype") or metadata.get("contentType"),
        total_size=total_size,
        offset=0,
        temp_path=temp_path,
        owner_id=current_user.id,
        expires_at=expires_at,
    )
    with Session(engine) as session:
        session.add(upload)
        session.commit()

    return Response(
        status_code=status.HTTP_201_CREATED,
        headers={
            **_base_headers(),
            "Location": f"{request.url.scheme}://{request.url.netloc}/uploads/tus/{upload_key}",
            "Upload-Offset": "0",
            "Upload-Length": str(total_size),
            "Upload-Expires": expires_at.isoformat(),
        },
    )


@tus_router.head("/{upload_key}")
def upload_offset(upload_key: str, request: Request, current_user: User = Depends(get_current_user)) -> Response:
    """Report how much has landed. This is what a resuming client asks first."""
    _require_tus_version(request)
    upload = _load_upload(upload_key, current_user)
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            **_base_headers(),
            "Upload-Offset": str(upload.offset),
            "Upload-Length": str(upload.total_size),
            "Upload-Expires": upload.expires_at.isoformat(),
        },
    )


@tus_router.patch("/{upload_key}")
async def append_chunk(upload_key: str, request: Request, current_user: User = Depends(get_current_user)) -> Response:
    """Append one chunk at the client's stated offset.

    The body is consumed as a stream and written straight through to the buffer,
    so a chunk of any size costs only _WRITE_CHUNK_BYTES of memory. Writes run in
    a worker thread to keep the event loop responsive.
    """
    _require_tus_version(request)

    if request.headers.get("Content-Type") != "application/offset+octet-stream":
        raise HTTPException(status_code=415, detail="Content-Type must be application/offset+octet-stream")

    raw_offset = request.headers.get("Upload-Offset")
    if raw_offset is None:
        raise HTTPException(status_code=400, detail="Upload-Offset header is required")
    try:
        client_offset = int(raw_offset)
    except ValueError:
        raise HTTPException(status_code=400, detail="Upload-Offset must be an integer")

    upload = _load_upload(upload_key, current_user)
    if client_offset != upload.offset:
        # The tus-defined signal to re-HEAD and resume from the real offset.
        raise HTTPException(status_code=409, detail=f"Offset mismatch: server is at {upload.offset}")

    temp_path = _safe_buffer_path(upload.temp_path)
    offset = upload.offset
    total_size = upload.total_size

    def _open_buffer():
        handle = open(temp_path, 'r+b')
        handle.seek(offset)
        return handle

    handle = await anyio.to_thread.run_sync(_open_buffer)
    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            if offset + len(chunk) > total_size:
                # Writing past the declared length would corrupt the file.
                raise HTTPException(status_code=413, detail="Chunk exceeds the declared Upload-Length")
            await anyio.to_thread.run_sync(handle.write, chunk)
            offset += len(chunk)
    finally:
        await anyio.to_thread.run_sync(handle.close)
        # Persist whatever landed, even on a mid-chunk disconnect, so the client
        # can resume from here instead of restarting.
        with Session(engine) as session:
            row = session.get(TusUpload, upload.id)
            if row:
                row.offset = offset
                row.updated_at = datetime.now()
                session.add(row)
                session.commit()

    headers = {**_base_headers(), "Upload-Offset": str(offset)}

    if offset < total_size:
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)

    # Complete: store it and hand back the file metadata so the client gets the
    # file id without a further round trip.
    upload.offset = offset
    result = await anyio.to_thread.run_sync(upload_service.finalize_tus_upload, upload)
    if result.data is None:
        return Response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers=headers,
            content=result.model_dump_json(by_alias=True),
            media_type="application/json",
        )
    return Response(
        status_code=status.HTTP_200_OK,
        headers=headers,
        content=result.model_dump_json(by_alias=True),
        media_type="application/json",
    )


@tus_router.delete("/{upload_key}")
def terminate_upload(upload_key: str, request: Request, current_user: User = Depends(get_current_user)) -> Response:
    """Abandon an upload and drop its buffer (tus termination extension)."""
    _require_tus_version(request)
    upload = _load_upload(upload_key, current_user)

    with contextlib.suppress(HTTPException, OSError):
        os.remove(_safe_buffer_path(upload.temp_path))

    with Session(engine) as session:
        row = session.get(TusUpload, upload.id)
        if row:
            session.delete(row)
            session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_base_headers())


def cleanup_expired_tus_uploads() -> int:
    """Drop expired, unfinished uploads and their buffers. Called at startup so
    abandoned 2 GB buffers cannot accumulate on disk indefinitely."""
    removed = 0
    try:
        with Session(engine) as session:
            expired = session.exec(
                select(TusUpload).where(
                    TusUpload.expires_at < datetime.now(),
                    TusUpload.uploaded_file_id == None,  # noqa: E711 - SQL NULL comparison
                )
            ).all()
            for upload in expired:
                with contextlib.suppress(HTTPException, OSError):
                    os.remove(_safe_buffer_path(upload.temp_path))
                session.delete(upload)
                removed += 1
            session.commit()
    except Exception as e:
        # Never block startup on housekeeping.
        logger.warning("Expired tus upload cleanup failed: %s", e)
        return removed

    if removed:
        logger.info("Reaped %d expired tus upload(s)", removed)
    return removed
