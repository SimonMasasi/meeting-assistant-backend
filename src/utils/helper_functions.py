def classify_file_type_to_folder(file_bytes: bytes) -> str:
        import magic
        extension = magic.from_buffer(file_bytes, mime=True).split('/')[-1]
        if extension in ['jpg', 'jpeg', 'png', 'gif']:
            return 'images/'
        elif extension in ['pdf', 'docx', 'txt']:
            return 'documents/'
        elif extension in ['mp4', 'avi', 'mov']:
            return 'videos/'
        else:
            return 'others/'
        
        

def _iter_file_chunks(file_stream, chunk_size: int = 1024 * 1024):
    while True:
        chunk = file_stream.read(chunk_size)
        if not chunk:
            break
        yield chunk