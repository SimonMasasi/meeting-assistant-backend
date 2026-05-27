import jwt
from config import SETTINGS
from datetime import datetime, timezone , timedelta
from src.modules.auth.models import User

class JWTAuth:
    def __init__(self, secret_key: str = SETTINGS.SECRET_KEY, algorithm: str = SETTINGS.JWT_ALGORITHM):
        self.secret_key = secret_key
        self.algorithm = algorithm

    def encode(self, payload: dict) -> str:
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode(self, token: str) -> dict:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm] , options={"verify_signature": True, "verify_exp": True})
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")
        
        
    def create_access_token_and_refresh_token(self, user: User, expires_delta: int = SETTINGS.JWT_ACCESS_TOKEN_EXPIRE_SECONDS):
        payload = {
            "user_id": user.id,
            "username": user.username,
            "exp": (datetime.now(tz=timezone.utc) + timedelta(seconds=expires_delta)).timestamp(),
            "iss": "meeting-assistant-backend"
        }
        
        access_payload = payload.copy()
        access_payload.update({"type": "access"})
        access_token = self.encode(access_payload)

        refresh_payload = payload.copy()
        refresh_payload.update({"type": "refresh"})
        refresh_token = self.encode(refresh_payload)

        return access_token, refresh_token , expires_delta
    
    
    def refresh_access_token(self, refresh_token: str) -> tuple[str , int]:
        decoded_payload = self.decode(refresh_token)
        if decoded_payload.get("type") != "refresh":
            raise ValueError("Invalid token type")
        
        user_id = decoded_payload.get("user_id")
        username = decoded_payload.get("username")
        
        new_access_payload = {
            "user_id": user_id,
            "username": username,
            "exp": (datetime.now(tz=timezone.utc) + timedelta(seconds=SETTINGS.JWT_ACCESS_TOKEN_EXPIRE_SECONDS)).timestamp(),
            "iss": "meeting-assistant-backend"
        }
        
        access_payload = new_access_payload.copy()
        access_payload.update({"type": "access"})
        access_token = self.encode(access_payload)

        return access_token, SETTINGS.JWT_ACCESS_TOKEN_EXPIRE_SECONDS   