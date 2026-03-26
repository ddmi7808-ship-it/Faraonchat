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

# Настройки
SECRET_KEY = "FARAON_GOLD_KEY_999"
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DATABASE_URL = "sqlite:///./faraon.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модели
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    sender = Column(String)
    recipient = Column(String)
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    async def connect(self, username: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[username] = websocket
    def disconnect(self, username: str):
        self.active_connections.pop(username, None)
    async def send_to(self, message: dict, to_user: str):
        if to_user in self.active_connections:
            await self.active_connections[to_user].send_json(message)

manager = ConnectionManager()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@app.get("/")
async def serve_home(): return FileResponse("index.html")

@app.post("/register")
def register(data: dict, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data['username']).first():
        raise HTTPException(400, "User exists")
    user = User(username=data['username'], hashed_password=pwd_context.hash(data['password']))
    db.add(user)
    db.commit()
    return {"status": "ok"}

@app.post("/login")
def login(data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data['username']).first()
    if not user or not pwd_context.verify(data['password'], user.hashed_password):
        raise HTTPException(400, "Wrong pass")
    return {"token": jwt.encode({"sub": user.username}, SECRET_KEY, ALGORITHM)}

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str, db: Session = Depends(get_db)):
    await manager.connect(username, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg = Message(sender=username, recipient=data['to'], content=data['content'])
            db.add(msg); db.commit()
            await manager.send_to({"from": username, "content": data['content']}, data['to'])
    except WebSocketDisconnect:
        manager.disconnect(username)
