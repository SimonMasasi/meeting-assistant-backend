MIME_SNIFF_BYTES = 2048


def classify_file_type_to_folder(file_bytes: bytes) -> str:
        # libmagic only ever looks at the head of the buffer, so callers holding a
        # large file may pass just the first MIME_SNIFF_BYTES instead of all of it.
        import magic
        extension = magic.from_buffer(file_bytes[:MIME_SNIFF_BYTES], mime=True).split('/')[-1]
        if extension in ['jpg', 'jpeg', 'png', 'gif']:
            return 'images/'
        elif extension in ['pdf', 'docx', 'txt']:
            return 'documents/'
        elif extension in ['mp4', 'avi', 'mov']:
            return 'videos/'
        else:
            return 'others/'
        
        

def iter_file_chunks(file_stream, chunk_size: int = 1024 * 1024):
    while True:
        chunk = file_stream.read(chunk_size)
        if not chunk:
            break
        yield chunk