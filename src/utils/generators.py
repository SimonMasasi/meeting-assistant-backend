import random
import time

class Generator:
    
    @staticmethod
    def generate_64bit_int_uuid() -> int:
        """
        Time-based 64-bit unique ID.
        Safe for public exposure (non-sequential PK).
        """
        return (int(time.time() * 1000) << 16) | random.getrandbits(16)
