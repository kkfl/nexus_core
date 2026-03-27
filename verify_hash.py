import httpx
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")
hash_str = "$argon2id$v=19$m=65536,t=3,p=4$ak0pxThnbE0JwXjPGQMAYA$EyPKAZZqxThlP6Oo3uoNDa/WtWFM+mHSSSrAUXqRnaBY"
print(f"Hash parsing test: {pwd_context.verify('password', hash_str)}")
