from src.utils.uploads.providers.local_uploads import LocalUploads
from src.utils.uploads.providers.rustf_uploads import RustfUploads
from src.shared.enums import FileTypeEnum
from src.utils.helper_functions import MIME_SNIFF_BYTES, iter_file_chunks
import contextlib
import magic
import hashlib
from config import SETTINGS


class UploadsManager:
    
    def __init__(self):
        self.provider = RustfUploads() if SETTINGS.USE_RUSTF_UPLOADS else LocalUploads()
        
    def upload_file(self, file_bytes: bytes, object_name: str):
        return self.provider.upload_file(file_bytes, object_name)

    def upload_stream(self, file_obj, object_name: str, size: int | None = None, source_path: str | None = None):
        """Store from an open file object instead of a bytes buffer. Used by the
        resumable tus path, where the file may be gigabytes."""
        return self.provider.upload_stream(file_obj, object_name, size, source_path)

    def get_file_as_bytes(self, file_path: str) -> bytes | None:
        return self.provider.get_file_as_bytes(file_path)

    def get_file_stream(self, file_path: str):
        return self.provider.get_file_stream(file_path)

    def get_file_to_path(self, file_path: str, dest_path: str) -> bool:
        """Stream a stored object down to a local file. Returns False when the
        object is missing. Lets callers work on large files by path."""
        file_stream = self.get_file_stream(file_path)
        if file_stream is None:
            return False
        try:
            with open(dest_path, 'wb') as destination:
                for chunk in iter_file_chunks(file_stream):
                    destination.write(chunk)
        finally:
            with contextlib.suppress(Exception):
                file_stream.close()
        return True

    def calculate_file_size(self, file_bytes: bytes) -> int:
        return len(file_bytes)

    def get_file_mimetype(self, file_bytes: bytes) -> str:
        return magic.from_buffer(file_bytes, mime=True)

    def mimetype_of_head(self, file_obj) -> str:
        """Mimetype from the head of an open file object; libmagic never needs
        more than that, so this stays O(1) regardless of file size."""
        head = file_obj.read(MIME_SNIFF_BYTES)
        file_obj.seek(0)
        return magic.from_buffer(head, mime=True)

    def calculate_file_hash(self, file_bytes: bytes) -> str:
        sha256_hash = hashlib.sha256()
        sha256_hash.update(file_bytes)
        return sha256_hash.hexdigest()

    def hash_stream(self, file_obj) -> str:
        """sha256 of an open file object, read incrementally so the file is never
        held in memory. Leaves the object rewound for the caller."""
        sha256_hash = hashlib.sha256()
        for chunk in iter_file_chunks(file_obj):
            sha256_hash.update(chunk)
        file_obj.seek(0)
        return sha256_hash.hexdigest()


    def classify_file_type_to_file_enum(self, file_name: str):


        images_extensions = ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "svg"]
        videos_extensions = ["mp4", "avi", "mov", "wmv", "flv", "mkv"]
        audio_extensions = ["mp3", "wav", "aac", "flac", "ogg", "m4a"]
        documents_extensions = ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf"]

        file_extension = file_name.split('.')[-1].lower()

        if file_extension in images_extensions:
            return FileTypeEnum.IMAGE.value
        elif file_extension in videos_extensions:
            return FileTypeEnum.VIDEO.value
        elif file_extension in audio_extensions:
            return FileTypeEnum.AUDIO.value
        elif file_extension in documents_extensions:
            return FileTypeEnum.DOCUMENT.value
        else:
            return FileTypeEnum.OTHER.value
    
    