from src.utils.uploads.providers.local_uploads import LocalUploads
from src.utils.uploads.providers.rustf_uploads import RustfUploads
from src.shared.enums import FileTypeEnum
import magic
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
        import hashlib
        sha256_hash = hashlib.sha256()
        sha256_hash.update(file_bytes)
        return sha256_hash.hexdigest()
    
    def classify_file_type_to_file_enum(self, file_bytes: bytes) -> FileTypeEnum:
        mimetype = self.get_file_mimetype(file_bytes)
        main_type = mimetype.split('/')[0]
        if main_type == 'image':
            return FileTypeEnum.IMAGE
        elif main_type == 'video':
            return FileTypeEnum.VIDEO
        elif main_type == 'audio':
            return FileTypeEnum.AUDIO
        elif main_type in ['application', 'text']:
            return FileTypeEnum.DOCUMENT
        else:
            return FileTypeEnum.OTHER
    
    