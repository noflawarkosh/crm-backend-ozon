from config import HASHSALT
from hashlib import pbkdf2_hmac
import random
import string


class Strings:
    @classmethod
    def hmac(cls, pwd: str) -> str:
        return pbkdf2_hmac('sha256', pwd.encode(), HASHSALT.encode(), 100000).hex()

    @classmethod
    def alphanumeric(cls, length: int) -> str:
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))
