from dotenv import load_dotenv
import os

load_dotenv()

DB_HOST = os.environ.get('DB_HOST')
DB_PORT = os.environ.get('DB_PORT')
DB_NAME = os.environ.get('DB_NAME')
DB_USER = os.environ.get('DB_USER')
DB_PASS = os.environ.get('DB_PASS')
HASHSALT = os.environ.get('HASHSALT')

S3KID = os.environ.get('S3KID')
S3KEY = os.environ.get('S3KEY')
S3BUCKET = os.environ.get('S3BUCKET')

ACCEPTABLE_IMAGE_TYPES = {
    'jpeg': 1048576 * 10,
    'png': 1048576 * 10,
    'jpg': 1048576 * 10,
    'webp': 1048576 * 10,
}

ACCEPTABLE_FILE_TYPES = {
    'mp4': 1048576 * 50,
    'mov': 1048576 * 50,
    'pdf': 1048576 * 10,
    'xlsx': 1048576 * 30,
    'docx': 1048576 * 15,
}

DEFAULT_MAX_FILE_SIZE = 1048576 * 25
