from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session, select
from src.shared.database import engine
from src.modules.auth.models import User
from src.utils.jwt_auth import JWTAuth

bearer_scheme = HTTPBearer()
jwt_auth = JWTAuth()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user_type: str = None
) -> User:
    try:
        payload = jwt_auth.decode(credentials.credentials)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    with Session(engine) as session:
        user = session.exec(select(User).where(User.id == payload["user_id"])).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if user_type and user.user_type.value != user_type:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return user
