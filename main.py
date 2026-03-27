import datetime
import os
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from jose import jwt

# Настройки безопасности
SECRET_KEY = "FARAON_GOLD_KEY_999"
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# База данных (автоматически создается файл faraon.db)
DATABASE_URL = "sqlite:///./faraon.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель пользователя
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

# Модель сообщения
class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    sender = Column(String)
    recipient = Column(String)
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Создание таблиц
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Разрешаем запросы со всех адресов (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Управление подключениями WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, username: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[username] = websocket
        print(f"DEBUG: {username} подключился")

    def disconnect(self, username: str):
        if username in self.active_connections:
            del self.active_connections[username]
            print(f"DEBUG: {username} отключился")

    async def send_to(self, message: dict, to_user: str):
        if to_user in self.active_connections:
            await self.active_connections[to_user].send_json(message)

manager = ConnectionManager()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Отдача фронтенда
@app.get("/")
async def serve_home():
    if not os.path.exists("index.html"):
        return {"error": "Файл index.html не найден в папке проекта!"}
    return FileResponse("index.html")

# РЕГИСТРАЦИЯ
@app.post("/register")
async def register(data: dict, db: Session = Depends(get_db)):
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Нужны имя и пароль")
    
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        print(f"DEBUG: Регистрация отклонена - {username} уже есть")
        raise HTTPException(status_code=400, detail="Такой пользователь уже существует")
    
    new_user = User(username=username, hashed_password=pwd_context.hash(password))
    db.add(new_user)
    db.commit()
    print(f"DEBUG: Пользователь {username} успешно создан")
    return {"status": "success"}

# ВХОД
@app.post("/login")
async def login(data: dict, db: Session = Depends(get_db)):
    username = data.get("username")
    password = data.get("password")
    
    user = db.query(User).filter(User.username == username).first()
    if not user or not pwd_context.verify(password, user.hashed_password):
        print(f"DEBUG: Ошибка входа для {username}")
        raise HTTPException(status_code=400, detail="Неверное имя или пароль")
    
    token = jwt.encode({"sub": user.username}, SECRET_KEY, algorithm=ALGORITHM)
    print(f"DEBUG: {username} вошел в систему")
    return {"token": token, "username": username}

# ЧАТ (WebSocket)
@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str, db: Session = Depends(get_db)):
    await manager.connect(username, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Сохраняем в базу
            new_msg = Message(
                sender=username, 
                recipient=data['to'], 
                content=data['content']
            )
            db.add(new_msg)
            db.commit()
            
            # Отправляем получателю
            await manager.send_to({
                "from": username, 
                "content": data['content']
            }, data['to'])
    except WebSocketDisconnect:
        manager.disconnect(username)
    except Exception as e:
        print(f"DEBUG: Ошибка WebSocket: {e}")
        manager.disconnect(username)
