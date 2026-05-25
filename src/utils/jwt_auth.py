import jwt
from config import SETTINGS
from datetime import datetime, timezone , timedelta


class JWTAuth:
    def __init__(self, secret_key: str = SETTINGS.SECRET_KEY, algorithm: str = SETTINGS.JWT_ALGORITHM):
        self.secret_key = secret_key
        self.algorithm = algorithm

    def encode(self, payload: dict) -> str:
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode(self, token: str) -> dict:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")
        
        
    def create_access_token_and_refresh_token(self, user , expires_delta: int = SETTINGS.JWT_ACCESS_TOKEN_EXPIRE_MINUTES):
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