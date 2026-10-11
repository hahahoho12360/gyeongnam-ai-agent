"""Firebase ID-token verification and ownership checks for private records."""
import os
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .db import get_store

bearer=HTTPBearer(auto_error=False)

def required_user(credentials: HTTPAuthorizationCredentials | None=Depends(bearer)) -> str:
    if not credentials or credentials.scheme.lower()!='bearer':
        raise HTTPException(401,'개인 기록을 사용하려면 익명 인증이 필요합니다.',headers={'WWW-Authenticate':'Bearer'})
    try:
        import firebase_admin
        from firebase_admin import auth
        if not firebase_admin._apps: get_store()
        decoded=auth.verify_id_token(credentials.credentials,check_revoked=True)
        uid=decoded.get('uid')
        if not isinstance(uid,str) or not uid: raise ValueError('Invalid UID')
        return uid
    except Exception:
        raise HTTPException(401,'인증이 만료되었거나 유효하지 않습니다. 다시 연결해 주세요.',headers={'WWW-Authenticate':'Bearer'}) from None

def owned(collection, doc_id, uid):
    row=get_store().get(collection,doc_id)
    if not row or row.get('owner_uid')!=uid:
        raise HTTPException(404,'본인의 기록을 찾을 수 없습니다.')
    return row

def public_config():
    key=os.getenv('FIREBASE_WEB_API_KEY','').strip()
    project=os.getenv('FIREBASE_PROJECT_ID','').strip()
    domain=os.getenv('FIREBASE_AUTH_DOMAIN','').strip() or (project+'.firebaseapp.com' if project else '')
    return {'enabled':bool(key and project),'config':{'apiKey':key,'projectId':project,'authDomain':domain} if key and project else {},
            'notice':'브라우저별 익명 계정으로 개인 기록을 보호합니다. 다른 기기나 브라우저 정보 삭제 후에는 기존 기록에 접근하지 못할 수 있습니다.'}
