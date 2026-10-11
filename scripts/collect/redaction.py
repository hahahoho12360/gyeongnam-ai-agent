"""Remove credentials from diagnostic strings before logging or persistence."""
from __future__ import annotations
import os
import re
from urllib.parse import quote, quote_plus

REDACTED = '[REDACTED]'
_SECRET_NAMES = ('DATA_GO_KR_SERVICE_KEY', 'OPENAI_API_KEY', 'ADMIN_REFRESH_TOKEN',
                 'GITHUB_TOKEN', 'GH_TOKEN', 'FIREBASE_SERVICE_ACCOUNT_JSON')
_FIELD = r'(?:service[_-]?key|api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|private_key)'

def redact_text(value: object, *, secrets=()) -> str:
    text=str(value)
    values=set(secrets) | {os.getenv(name,'') for name in _SECRET_NAMES}
    for secret in sorted((s for s in values if s and len(s)>=8),key=len,reverse=True):
        for encoded in (secret,quote(secret,safe=''),quote_plus(secret),quote(quote(secret,safe=''),safe='')):
            text=text.replace(encoded,REDACTED)
    text=re.sub(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',REDACTED,text,flags=re.S)
    # JSON/dict quoted values, including escaped newlines in private keys.
    text=re.sub(r'(["\']'+_FIELD+r'["\']\s*:\s*)(["\'])(.*?)(\2)',
                lambda m:m[1]+m[2]+REDACTED+m[2],text,flags=re.I|re.S)
    # Query parameters, unquoted assignments and percent-encoded URL forms.
    text=re.sub(r'('+_FIELD+r'(?:=|%3D))(.+?)(?=&|%26|\s|["\'<>]|$)',
                lambda m:m[1]+REDACTED,text,flags=re.I)
    text=re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+',r'\1'+REDACTED,text)
    return text

def redact(value):
    if isinstance(value,str): return redact_text(value)
    if isinstance(value,dict):
        return {k:REDACTED if re.fullmatch(_FIELD,str(k),re.I) else redact(v) for k,v in value.items()}
    if isinstance(value,list): return [redact(v) for v in value]
    if isinstance(value,tuple): return tuple(redact(v) for v in value)
    return value
