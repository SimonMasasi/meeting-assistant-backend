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