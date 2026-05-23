import bcrypt


class PasswordManager:
    @staticmethod
    def hash_password(plain_password: str) -> str:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(plain_password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    

    def is_strong_password(self, password: str):
        if len(password) < 8:
            return False , "Password must be at least 8 characters long"
        if not any(char.isdigit() for char in password):
            return False , "Password must contain at least one digit"
        if not any(char.isalpha() for char in password):
            return False , "Password must contain at least one letter"
        if not any(char in "!@#$%^&*()-_=+[]{}|;:'\",.<>?/" for char in password):
            return False , "Password must contain at least one special character"
        return True , "Password is strong"