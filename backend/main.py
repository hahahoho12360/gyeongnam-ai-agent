from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .routers import data, conversations, analytics, chat, admin, meta
from .db import get_store
from .demo import seed_demo
import os
@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.use_memory_db and os.getenv('DEMO_SEED_ON_START','false').lower() in {'1','true','yes','on'}:
        seed_demo(get_store())
    yield

app=FastAPI(title='경상남도 생활·주거·부동산·상권 변화 AI 비서',version='3.8.1',description='AI Agent 과제용 FastAPI 백엔드',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins or ['*'],allow_credentials=False,allow_methods=['*'],allow_headers=['*'])
app.include_router(data.router); app.include_router(conversations.router); app.include_router(analytics.router); app.include_router(chat.router); app.include_router(admin.router); app.include_router(meta.router)
@app.get('/')
def root(): return {'service':'gyeongnam-ai-agent','status':'ok','docs':'/docs','db_mode':'memory' if settings.use_memory_db else 'firestore'}
@app.get('/health')
def health(): return {'status':'ok'}



@app.get('/api/auth/config',tags=['authentication'])
def auth_config():
    from .auth import public_config
    return public_config()
