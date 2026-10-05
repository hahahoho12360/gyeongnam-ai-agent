# Checkpoint 3.0 — PC를 꺼도 계속되는 GitHub Actions Cloud Rollout

## 목적

로컬 PC의 PowerShell에서 장시간 Backfill을 돌리는 대신 GitHub의 클라우드 실행기에서 처리합니다.
PC를 종료해도 GitHub Actions는 계속 실행됩니다.

GitHub-hosted runner의 한 job은 최대 6시간이므로, v3.0은 한 job을 약 270분에서 스스로 종료하고
진행상태를 Firestore `rollout_jobs`에 저장합니다. 남은 일이 있으면 현재 workflow가 다음
`workflow_dispatch` 실행을 자동으로 생성합니다. 따라서 한 번 시작한 뒤 사람이 5개 Batch마다
다시 명령을 입력할 필요가 없습니다.

## 왜 로컬 resume 파일을 사용하지 않나

GitHub Actions runner는 실행마다 새 가상머신입니다. `.rollout-xxx.json` 같은 로컬 파일은 다음
실행에 자동으로 남지 않습니다. v3.0은 진행상태를 Firestore에 저장합니다.

- `rollout_jobs/cloud_changwon_v30`
- `rollout_jobs/cloud_gyeongnam_v30`

각 source-month-batch가 성공할 때마다 cursor가 저장됩니다.

## 최초 1회 준비 — Repository Secrets 3개

GitHub 저장소 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
에서 다음 3개를 만듭니다.

1. `FIREBASE_PROJECT_ID`
   - Firebase Console의 프로젝트 ID 값만 입력합니다.

2. `DATA_GO_KR_SERVICE_KEY`
   - 현재 `.env`에서 정상 작동 중인 공공데이터포털 일반 인증키를 입력합니다.

3. `FIREBASE_SERVICE_ACCOUNT_JSON`
   - Firebase 서비스 계정 JSON 파일의 **전체 내용**을 secret 값으로 붙여넣습니다.
   - 이 JSON을 GitHub 저장소 파일로 업로드하면 안 됩니다.
   - 채팅에도 붙이지 않습니다.

OpenAI API 키는 데이터 Backfill workflow에서 사용하지 않으므로 등록할 필요가 없습니다.

## 최초 실행

GitHub 저장소 → `Actions` → `Gyeongnam AI Cloud Rollout v3.0` → `Run workflow`

권장 첫 실행:

- scope: `changwon`
- reset: `false`
- batch_size: `10`

창원 Cloud 실행이 완주한 뒤 경남 전체:

- scope: `gyeongnam`
- reset: `false`
- batch_size: `10`

`Run workflow`를 한 번 누른 뒤에는 PC를 꺼도 됩니다.

## 자동 연속 실행 구조

```
GitHub Actions Run #1
  ↓ 약 270분 작업
Firestore rollout_jobs에 cursor 저장
  ↓ 남은 일 있음
workflow_dispatch 자동 생성
  ↓
GitHub Actions Run #2
  ↓
...
  ↓
Historical 완료
  ↓
Snapshot 완료
  ↓
경남이면 Composite Index
  ↓
Data Quality
  ↓
status = complete
```

## 오류 시

- timeout / 연결 오류 / 429 / 5xx: 제한적으로 재시도합니다.
- 반복 가능한 일시 오류가 계속되면 `needs_continue` 상태로 다음 run에 넘깁니다.
- 400/401/403, 잘못된 API URL/권한처럼 기다려도 해결되지 않는 오류는 `blocked`로 멈춥니다.
- `blocked`이면 무한하게 비용을 쓰지 않습니다.

Firestore에서 상태 확인:

`rollout_jobs/cloud_gyeongnam_v30`

주요 필드:

- `status`: running / needs_continue / blocked / complete
- `stage`: historical / snapshot / indexes / quality / done
- `cursor`: 현재 단계에서 완료한 task 위치
- `last_task`
- `last_error`
- `total_success_tasks`
- `total_skipped_tasks`

## reset은 함부로 누르지 않기

`reset=true`는 Firestore rollout cursor를 처음으로 되돌립니다.
이미 저장된 `monthly_data`를 삭제하지는 않으며 v3.0은 해당 source가 이미 존재하는 문서를 확인해
재호출을 건너뛰지만, 정상 진행 중이라면 reset할 이유가 없습니다.

## GitHub Actions 시간/비용 참고

GitHub-hosted runner 한 job은 최대 6시간입니다. v3.0은 270분 자체 제한을 사용합니다.
공개 저장소의 표준 GitHub-hosted runner는 무료이며, 비공개 저장소는 GitHub 요금제별 포함 시간이
적용됩니다. 장시간 경남 전체 초기 Backfill은 Actions 사용 시간을 소모할 수 있으므로 GitHub의
`Settings → Billing`에서도 Actions 사용량을 확인하세요.

## 완료 결과

완료 시:

- Firestore `rollout_jobs/...` → `status=complete`
- Firestore `rollout_reports/...` → Data Quality 결과
- Actions artifact → `cloud_rollout_status.json`, 최종 summary JSON

이후 단계는 FastAPI/Function Calling/프론트엔드/MCP/배포입니다.
