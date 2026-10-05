# 배포 절차 요약

## Render (백엔드)
- 저장소 연결 → Blueprint(render.yaml) 또는 Web Service
- Secret: OPENAI_API_KEY, FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_PROJECT_ID, ALLOWED_ORIGINS, ADMIN_REFRESH_TOKEN
- 배포 후 `/health`, `/docs` 확인
- 무료 서비스 Cold Start 안내 문구를 UI에 유지

## Vercel (프론트)
- 같은 저장소 Import
- Build Command: `node scripts/build-config.mjs`
- Output Directory: `frontend`
- 환경변수 `API_BASE_URL=https://<render>.onrender.com`
- 배포 후 Render의 ALLOWED_ORIGINS에 Vercel URL 추가

## GitHub Actions
- daily/monthly workflow의 Secrets에 Firebase와 공공데이터 서비스키/URL을 입력
- 수동 `workflow_dispatch`로 먼저 검증한 뒤 schedule 사용
