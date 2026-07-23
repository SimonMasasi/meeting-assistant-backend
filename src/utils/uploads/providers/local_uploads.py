import os
import shutil
from src.utils.helper_functions import MIME_SNIFF_BYTES, classify_file_type_to_folder
from src.utils.generators import Generator

class LocalUploads:
    
    def __init__(self):
        self.upload_folder = "uploads_media"
        os.makedirs(self.upload_folder, exist_ok=True)
        self.upload_root = os.path.realpath(os.path.abspath(self.upload_folder))

    def _resolve_safe_path(self, file_path: str) -> str | None:
        candidate = os.path.abspath(file_path)
        candidate_real = os.path.realpath(candidate)
        if os.path.commonpath([self.upload_root, candidate_real]) != self.upload_root:
            return None
        return candidate_real
        

    def upload_file(self, file_bytes: bytes, object_name: str):
        file_type_folder = classify_file_type_to_folder(file_bytes)
        unique_identifier = Generator.generate_64bit_int_uuid()
        
        # change the object name to  the unique identifier and keep the original file extension
        original_extension = os.path.splitext(object_name)[1]
        object_name = f"{unique_identifier}{original_extension}"
        folder_path = os.path.join(self.upload_folder, file_type_folder)
        os.makedirs(folder_path, exist_ok=True)
        
        file_path = os.path.join(folder_path, object_name)
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
        
        return True , "File uploaded successfully" , file_path

    def _destination_path(self, file_obj, object_name: str) -> str:
        """Pick the same folder/name a byte upload would, sniffing only the head."""
        head = file_obj.read(MIME_SNIFF_BYTES)
        file_obj.seek(0)
        file_type_folder = classify_file_type_to_folder(head)
        unique_identifier = Generator.generate_64bit_int_uuid()
        original_extension = os.path.splitext(object_name)[1]

        folder_path = os.path.join(self.upload_folder, file_type_folder)
        os.makedirs(folder_path, exist_ok=True)
        return os.path.join(folder_path, f"{unique_identifier}{original_extension}")

    def upload_stream(self, file_obj, object_name: str, size: int | None = None, source_path: str | None = None):
        """Store from an open file object without materializing it in memory.

        When source_path is given and sits on the same filesystem as the upload
        root (the tus buffer case) the file is moved rather than copied, so a
        2 GB upload costs no extra I/O and no extra disk.
        """
        try:
            file_path = self._destination_path(file_obj, object_name)

            if source_path is not None:
                try:
                    file_obj.close()
                    os.replace(source_path, file_path)
                    return True , "File uploaded successfully" , file_path
                except OSError:
                    # Cross-device (or otherwise un-renameable): fall back to a copy.
                    file_obj = open(source_path, 'rb')

            with open(file_path, 'wb') as destination:
                shutil.copyfileobj(file_obj, destination, length=1024 * 1024)

            return True , "File uploaded successfully" , file_path
        except OSError as e:
            return False , f"Error uploading file: {str(e)}" , None

    def get_file_as_bytes(self, file_path: str) -> bytes | None:
        safe_path = self._resolve_safe_path(file_path)
        if safe_path is None or not os.path.exists(safe_path):
            return None

        with open(safe_path, 'rb') as f:
            file_bytes = f.read()
        
        return file_bytes

    def get_file_stream(self, file_path: str):
        safe_path = self._resolve_safe_path(file_path)
        if safe_path is None or not os.path.exists(safe_path):
            return None
        return open(safe_path, 'rb')