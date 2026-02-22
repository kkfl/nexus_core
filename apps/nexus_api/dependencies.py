import json
from datetime import datetime, timedelta
from typing import Optional, Union, Any, List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from packages.shared.db import get_db
from packages.shared.models import User, ApiKey, Agent
from packages.shared.config import settings

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None
        
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    return user

async def get_current_agent_by_key(
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> Optional[Agent]:
    if not api_key:
        return None
        
    key_hash = get_password_hash(api_key) # Typically you'd use a simpler hash like SHA256 for fast lookup, but bcrypt works.
    # WAIT! bcrypt generates a different salt every time. We cannot use bcrypt to *lookup* an API key directly if we only store the hash.
    # We must store the api_key in a way that we can look it up, OR we have to iterate all keys. 
    # Proper way for API keys: The key should have an ID prefix e.g., "ak_1_xyz". We look up ID 1, then verify the "xyz" part with bcrypt.
    
    # For simplicity in this demo, since API keys are often passed as plain or hashed with sha256 to allow direct lookup:
    import hashlib
    fast_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == fast_hash))
    key_record = result.scalars().first()
    
    if key_record and key_record.owner_type == 'agent':
        agent_res = await db.execute(select(Agent).where(Agent.id == key_record.owner_id))
        return agent_res.scalars().first()
    
    return None

async def get_current_identity(
    user: Optional[User] = Depends(get_current_user),
    agent: Optional[Agent] = Depends(get_current_agent_by_key)
) -> Union[User, Agent]:
    if user:
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        return user
    if agent:
        if not agent.is_active:
            raise HTTPException(status_code=400, detail="Inactive agent")
        return agent
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

class RequireRole:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return current_user
