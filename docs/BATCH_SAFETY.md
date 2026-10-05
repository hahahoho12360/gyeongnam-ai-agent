# Batch 안전장치 — Checkpoint 2.8

## 왜 필요한가

남양동 1개 지역 Pilot은 성공했지만, 경남 Master는 523개 지역이다. 실수로 523개 × 여러 달 × 여러 Source를 한 번에 실행하면 API/Firestore 사용량이 급증할 수 있다. 따라서 Backfill은 작은 Batch로 확대한다.

## 핵심 규칙

1. `--region`, `--sigungu-prefix`, `--all-regions` 중 하나가 없으면 Backfill은 실행되지 않는다.
2. `--max-regions` 기본값은 5다.
3. `--batch-size` 기본값은 5다.
4. 여러 달 Backfill에서는 Snapshot source(`apartment_basic`, `building_register`, `commerce`)를 거부한다.
5. Snapshot은 `--snapshot-only`로 한 달만 실행한다.
6. Backfill 중 Composite Index 재계산은 자동 지연한다.
7. Resume key는 지역 Batch scope를 포함해 서로 다른 Batch가 충돌하지 않는다.
8. Firestore quota 오류가 발생하면 즉시 중단하고 Resume 파일을 보존한다.

## 1. 아무 작업 없이 계획만 보기

```powershell
python scripts/backfill.py --start 2025-09 --end 2026-09 --historical-only --sigungu-prefix 4812 --max-regions 5 --batch-size 5 --dry-run-plan
```

`--dry-run-plan`은 API 호출과 Firestore 쓰기를 전혀 하지 않는다.

## 2. 창원권 첫 5개 지역 Historical 시험

```powershell
python scripts/backfill.py --start 2025-09 --end 2026-09 --historical-only --sigungu-prefix 4812 --max-regions 5 --batch-size 5 --resume-file .backfill-changwon-5.json
```

## 3. 다음 5개 지역

```powershell
python scripts/backfill.py --start 2025-09 --end 2026-09 --historical-only --sigungu-prefix 4812 --region-offset 5 --max-regions 5 --batch-size 5 --resume-file .backfill-changwon-next5.json
```

## 4. 20개 지역을 5개씩 내부 Batch 처리

```powershell
python scripts/backfill.py --start 2025-09 --end 2026-09 --historical-only --sigungu-prefix 4812 --max-regions 20 --batch-size 5 --resume-file .backfill-changwon-20.json
```

## 5. Snapshot은 한 달만

```powershell
python scripts/backfill.py --start 2026-10 --end 2026-10 --snapshot-only --sigungu-prefix 4812 --max-regions 5 --batch-size 5 --resume-file .snapshot-changwon-5.json
```

## 6. 정확한 법정지역코드 몇 개만 직접 지정

```powershell
python scripts/backfill.py --start 2025-09 --end 2026-09 --historical-only --region 4812313300 --region 4812312700 --max-regions 2 --batch-size 2 --resume-file .backfill-two-regions.json
```

## 7. 경남 전체는 최종 단계에서만

경남 전체는 반드시 먼저 `--dry-run-plan`으로 예상 지역 수를 확인한다. 이후 명시적으로 충분한 `--max-regions`와 작은 `--batch-size`를 사용한다.

```powershell
python scripts/backfill.py --start 2022-10 --end 2026-09 --historical-only --all-regions --max-regions 523 --batch-size 10 --dry-run-plan
```

실행은 계획을 확인한 뒤에만 `--dry-run-plan`을 제거한다.
