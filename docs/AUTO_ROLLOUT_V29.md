# Checkpoint 2.9 — 창원/경남 자동 Rollout

## 목적
남양동 Pilot 이후 사람이 5개/다음 5개/20개를 반복 입력하지 않아도 한 명령으로 창원시 또는 경상남도 전체를 단계적으로 처리한다.

## 핵심 원칙
- Historical: `population`, `age_population`, `single_household`, `apt_sale`, `apt_rent`
- Snapshot: `apartment_basic`, `building_register`, `commerce`
- 기본 Historical 기간: 2022-10 ~ 실행일의 전월
- Snapshot은 마지막 확정월 문서에 결합하되 실제 조회일은 `freshness.sources.*.source_as_of`로 보존
- batch size 기본 5
- Resume 자동 사용
- 일시 실패/Quota는 제한 횟수만 자동 재시도
- 창원 단계 Composite Index는 보류, 경남 전체 완료 후 계산

## 가장 쉬운 실행
### 창원시 전체
PowerShell에서:
```powershell
python scripts/auto_rollout.py --scope changwon
```
또는 Windows 탐색기에서 `scripts/run_changwon_v29.bat` 실행.

### 경상남도 전체
```powershell
python scripts/auto_rollout.py --scope gyeongnam
```
또는 `scripts/run_gyeongnam_v29.bat` 실행.

## 계획만 보기
```powershell
python scripts/auto_rollout.py --scope changwon --dry-run
```

## 중단되면
동일한 명령을 다시 실행한다. 다음 Resume 파일이 유지된다.
- `.rollout-changwon-historical.json`
- `.rollout-changwon-snapshot.json`
- `.rollout-gyeongnam-historical.json`
- `.rollout-gyeongnam-snapshot.json`

## 로그/결과
- `logs/rollout-changwon.log`
- `logs/rollout-gyeongnam.log`
- `artifacts/rollout_changwon_summary.json`
- `artifacts/rollout_gyeongnam_summary.json`

## 비용 안전
Blaze에서도 batch=5를 기본으로 유지한다. 프로그램이 중단돼도 Resume로 이어서 처리하므로 처음부터 다시 돌릴 필요가 없다.
