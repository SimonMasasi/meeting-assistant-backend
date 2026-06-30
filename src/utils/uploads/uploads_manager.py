from src.utils.uploads.providers.local_uploads import LocalUploads
from src.utils.uploads.providers.rustf_uploads import RustfUploads
from src.shared.enums import FileTypeEnum
import magic
import hashlib
from config import SETTINGS


class UploadsManager:
    
    def __init__(self):
        self.provider = RustfUploads() if SETTINGS.USE_RUSTF_UPLOADS else LocalUploads()
        
    def upload_file(self, file_bytes: bytes, object_name: str):
        return self.provider.upload_file(file_bytes, object_name)
    
    def get_file_as_bytes(self, file_path: str) -> bytes | None:
        return self.provider.get_file_as_bytes(file_path)

    def get_file_stream(self, file_path: str):
        return self.provider.get_file_stream(file_path)
    
    def calculate_file_size(self, file_bytes: bytes) -> int:
        return len(file_bytes)
    
    def get_file_mimetype(self, file_bytes: bytes) -> str:
        return magic.from_buffer(file_bytes, mime=True)
    
    def calculate_file_hash(self, file_bytes: bytes) -> str:
        sha256_hash = hashlib.sha256()
        sha256_hash.update(file_bytes)
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
    
    