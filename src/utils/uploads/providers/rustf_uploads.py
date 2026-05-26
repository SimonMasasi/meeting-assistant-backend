import io
import os

import boto3
from botocore.client import Config
from config import SETTINGS
from src.utils.helper_functions import classify_file_type_to_folder
from src.utils.generators import Generator


import logging
logger = logging.getLogger(__name__)


class RustfUploads:
    def __init__(self):
        self.bucket_name = SETTINGS.RUSTF_BUCKET_NAME
        self.s3_client = boto3.client(
            's3',
            endpoint_url=SETTINGS.RUSTF_URL,
            aws_access_key_id=SETTINGS.RUSTF_ACCESS_KEY,
            aws_secret_access_key=SETTINGS.RUSTF_SECRET_KEY,
            config=Config(signature_version='s3v4')
        )
    
        
    def create_s3_bucket(self , bucket_name=None):
        
        if bucket_name is None:
            bucket_name = self.bucket_name
        
        try:
            
            #check if bucket already exists
            existing_buckets = self.s3_client.list_buckets()
            if any(bucket['Name'] == bucket_name for bucket in existing_buckets.get('Buckets', [])):
                logger.info(f"Bucket '{bucket_name}' already exists.")
                return True
            
            self.s3_client.create_bucket(Bucket=bucket_name)
            logger.info(f"Bucket '{bucket_name}' created successfully.")
            
            return True
        except Exception as e:
            logger.error(f"Error creating bucket: {e}")
            return False

    def upload_file(self, file_bytes: bytes, object_name: str):
        try:
            self.create_s3_bucket()
            file_type_folder = classify_file_type_to_folder(file_bytes).rstrip('/')
            unique_identifier = Generator.generate_64bit_int_uuid()
            original_extension = os.path.splitext(object_name)[1]
            object_name = f"{file_type_folder}/{unique_identifier}{original_extension}"
            self.s3_client.upload_fileobj(io.BytesIO(file_bytes), self.bucket_name, object_name)
            return True , "File uploaded successfully" , object_name
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return False , f"Error uploading file: {str(e)}" , None
        
        
    def get_file_as_bytes(self, file_path: str) -> bytes | None:
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_path)
            file_bytes = response['Body'].read()
            return file_bytes
        except Exception as e:
            logger.error(f"Error retrieving file: {e}")
            return None    
        
    