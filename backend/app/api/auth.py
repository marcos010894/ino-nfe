from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from jose import jwt, JWTError
from app.models.database import get_session
from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioCreate, UsuarioLogin, UsuarioResponse, Token
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Autenticação"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> Usuario:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    usuario = session.exec(select(Usuario).where(Usuario.email == email)).first()
    if usuario is None:
        raise credentials_exception
    return usuario

@router.post("/register", response_model=UsuarioResponse)
def register(user_in: UsuarioCreate, session: Session = Depends(get_session)):
    # Verifica se já existe o email
    user_db = session.exec(select(Usuario).where(Usuario.email == user_in.email)).first()
    if user_db:
        raise HTTPException(status_code=400, detail="Email já cadastrado.")
    
    novo_usuario = Usuario(
        nome=user_in.nome,
        email=user_in.email,
        senha_hash=get_password_hash(user_in.senha)
    )
    session.add(novo_usuario)
    session.commit()
    session.refresh(novo_usuario)
    return novo_usuario

@router.post("/login", response_model=Token)
def login(user_in: UsuarioLogin, session: Session = Depends(get_session)):
    user = session.exec(select(Usuario).where(Usuario.email == user_in.email)).first()
    if not user or not verify_password(user_in.senha, user.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
        )
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UsuarioResponse)
def get_me(current_user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)):
    import secrets
    if not current_user.token_integracao:
        current_user.token_integracao = secrets.token_urlsafe(32)
        session.add(current_user)
        session.commit()
        session.refresh(current_user)
    return current_user
