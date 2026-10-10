# 창원 v3.6 공식 경계 검증 및 적용 안내

작성: 2026-10-10. 이번 제출 범위: 창원, ANALYSIS_SCOPE_PREFIX=4812.
이 ZIP은 아직 적용하지 않은 v3.5를 대체한다. v3.4까지 적용된 프로젝트에 v3.6만 덮어쓰면 된다.
Firebase와 Render에 이번 변경은 아직 적용하지 않았다.

## 검증 결론

코드·테스트 준비는 완료했지만 **인접지역 전체 검증은 실패**했다.
공식 파일이라는 사실과 도형의 품질 통과 여부를 구분한다.
검증을 통과하지 못한 인접지역 결과를 Firebase에 저장하지 않는다.

| 검사 | 실측 결과 | 판정 |
|---|---|---|
| 첨부 SHP/SHX/DBF/PRJ | 구성 파일 존재, EUC-KR 속성 읽기 성공 | 통과 |
| 좌표계 | PRJ의 EPSG:5186, EPSG:4326 변환, EPSG:5179 길이/면적 계산 | 통과 |
| 원천 버전 | LSMD_ADM_SECT_UMD_48_202609 | 2026년 9월 파일명 버전; 개별 변경 기준일은 미확인 |
| 경남 전체 레코드 | 547개, 숫자 8자리 읍면동 코드 546개 | 오류 레코드 1개 별도 기록 |
| 전체 도형 자체 유효성 | 7개 자체 교차 오류, 모두 창원 밖 | 경남 전체 운용 전 해결 필요 |
| 창원 경계 | 204개, 모두 숫자 코드/유효한 개별 도형 | 통과 |
| 기존 창원 snapshot | 181개 모두 경계 코드·이름 일치 | 통과 |
| snapshot 누락 | 공식 경계에는 존재하나 snapshot에는 없는 23개 | 보완 필요 |
| 누락 발생 코드 | 읍/면/동으로 끝나는 이름만 받는 필터가 '가' 지역 제외 | 코드 수정 완료 |
| 창원 도형 간 면적 겹침 | 66쌍, 투영 계산 최대 21,095.5466㎡ | 실패 |
| 겹침 제외 경계 공유 관계 | 467쌍, 대칭 관계, 자기 자신 0건 | 계산 조건 확인; 전체 실제 인접성 확정은 아님 |
| 원본 좌표 교차검산 | 원본 EPSG:5186에서 467쌍/겹침 66쌍 동일 | 변환 오류로 생긴 문제가 아님 |
| 고립 후보 | 토월동·우산동·현동·연도동 4개 | 실제 고립을 의미하지 않음; 겹침 때문에 관계 제외 가능 |
| 자동테스트 | 66개 통과 | 코드 통과, 실제 자료 검증 실패와 별개 |
| Firebase 쓰기/실서비스 배포 | 0건/미실시 | 변경 전 상태 |

원본 SHA256: 7d6574a85aa629089efa1a3f76675df6ab8312a5aec2e0367db02750afd97d73
공식 출처: https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?dsId=30603
첨부 ZIP을 사용자 제공 공식 원본으로 취급했다. 별도 재다운로드 또는 제공기관의 수정 이력 확인은 하지 않았다.

## 이번 ZIP의 파일

- data/boundaries/gyeongnam_legal_official_202609.geojson: 경남 원본의 모든 레코드를 변환, 좌표 단순화/반올림/도형 수선 없음.
- 같은 이름의 .provenance.json: 좌표계, 인코딩, 원본·변환본 해시, 원본 자체 오류 기록.
- official_boundary_verification_summary.json: 전체 검사 요약.
- gyeongnam_official_inventory_202609.json: 전체 코드·이름·도형 유효성 목록.
- changwon_regions_snapshot.json: 이전 첨부 /api/analytics/regions의 181개 snapshot. 실시간 DB 목록은 아님.
- changwon_missing_regions_202609.json: 누락 23개 후보와 월별 데이터 미수집 표시.
- changwon_boundary_master_202609.json: 204개 오프라인 대조 목록. **이 파일 전체를 Firebase에 덮어쓰지 않는다.**
- changwon_official_existing181_validation.json: 기존 181개 기준 결과(미대응 23개, 겹침 58쌍).
- changwon_official_boundary204_validation.json: 누락 후보 포함 204개 기준 결과(미대응 0, 겹침 66쌍).
- changwon_raw_topology_crosscheck.json: 원본 좌표 독립 교차검산 결과.
- changwon_overlap_review_202609.geojson: 겹침 66쌍의 실제 교차 도형. QGIS 등에서 원본 레이어와 함께 열어 위치 확인 가능.

updates는 검토용 후보이며 검증 실패 상태다. 보고서의 updates를 직접 Firebase에 복사하지 않는다.
경남 전체 숫자 코드 546개를 현재 현존 법정동 수로 확정하지 않는다. 별도 최신 법정동 코드·폐지 상태 대조는 아직 하지 않았다.

## 코드 변경

1. SHP ZIP 변환기: EUC-KR 속성, PRJ 좌표계 해석, 단순화 없는 변환, 원본 오류와 해시 기록.
2. 검증기: 경남 inventory, 창원 지역 대조, 누락 목록, 겹침 검토 레이어 생성. DB 접근 없음.
3. 인접 계산: 1m 이상 공유 경계선만 인정. 점 접촉은 제외. 0.01㎡ 초과 면적 겹침은 오류로 기록하고 해당 쌍 제외. 이 기준은 계산의 명시적 조건이며 제공기관의 법정 기준이 아니다.
4. 범위 밖 잘못된 코드: COL_ADM_SE로 범위 밖임을 확인 가능한 경우 따로 기록. 창원 오류까지 무시하는 기능은 아니다.
5. 적용 보호: 검증 보고서를 먼저 저장하고 --apply 명시 시에만 저장 시도. snapshot/진단 파일/검증 실패는 거부. 실제 Firestore만 허용.
6. 정상 검증 후 적용 시: 백업 파일 생성 및 500건 이하 Firestore batch로 원자적 업데이트. 현재는 검증 실패이므로 이 경로를 실행하지 않는다.
7. 지역목록 생성기: '대성동1가' 등 법정동도 받아들이며 기존 neighbors/centroid/추가 메타데이터를 보존하도록 merge.
8. 비교 응답: 모델 답변 후 저장 데이터의 인구·비교 대상·기간·차이/비교 불가 사유를 보완하고 대화에 저장.
9. 실제 월별 수치가 없는 지역에 인구·지수를 만들어 넣지 않음. 기존 유사도 방식의 결측치 0 대체 한계도 표시.

## 사용자가 지금 실행할 순서

### 1. 파일 적용

기존 프로젝트 폴더를 복사해 백업한다.
v3.6 ZIP을 임시 폴더에 풀면 backend/scripts/tests/docs/data가 보인다.
이 폴더들과 requirements-spatial.txt를 기존 gyeongnam-ai-agent 루트에 같은 경로로 덮어쓴다.
프로젝트 안에 gyeongnam-ai-agent를 한 겹 더 만들지 않는다.
v3.5 ZIP은 따로 적용하지 않는다. .env와 자격증명 파일은 이번 ZIP에 포함하지 않았다.
ANALYSIS_SCOPE_PREFIX=4812를 유지한다.

### 2. VS Code 터미널에서 설치와 테스트

기존 프로젝트를 VS Code로 열고 해당 프로젝트의 기존 Python 가상환경 터미널에서 실행한다.

```powershell
python -m pip install -r requirements-spatial.txt pytest
python -m pytest -q
```

프로젝트 기본 패키지가 설치되지 않은 환경이면 먼저 `python -m pip install -r requirements.txt`를 실행한다.
이 작업 환경의 결과는 `66 passed`다. 프로젝트 다른 변경이 있으면 테스트 수는 달라질 수 있다.

### 3. 공식 자료 검증 결과 재현 (Firebase 연결 없이 가능)

```powershell
python scripts/verify_official_boundaries.py
```

이번 원본의 정상적인 재현 출력:

```text
source_records: 547
valid_code_records: 546
changwon_boundaries: 204
missing_snapshot_regions: 23
firestore_applied: false
검증 통과: False
```

종료코드 2는 검증기 작동 실패가 아니라 **자료 검증 실패**를 의미한다. 보고서는 생성된다.
이 단계는 Firebase를 읽거나 쓰지 않는다. 필터를 느슨하게 하거나 임의 buffer/좌표 반올림으로 통과시키지 않는다.

원본부터 변환을 재현하려면 사용자가 받은 ZIP의 실제 경로를 넣는다. 포함된 변환본을 사용하는 경우 이 단계는 생략한다.

```powershell
python scripts/convert_legal_boundaries.py "원본ZIP의 실제 경로\LSMD_ADM_SECT_UMD_경남.zip" data/boundaries/gyeongnam_legal_official_202609.geojson
python scripts/verify_official_boundaries.py
```

### 4. 코드 변경 GitHub 업로드 및 Render 확인

```powershell
git status --short
git add backend/analysis.py backend/comparison_evidence.py backend/routers/chat.py scripts/build_neighbors.py scripts/bootstrap_regions.py scripts/bootstrap_regions_file.py scripts/region_master_utils.py scripts/convert_legal_boundaries.py scripts/verify_official_boundaries.py requirements-spatial.txt tests/test_neighbors.py tests/test_comparison_evidence.py tests/test_region_file_bootstrap.py tests/test_boundary_conversion.py docs/CHANGWON_BOUNDARIES_V36.md data/boundaries/gyeongnam_legal_official_202609.geojson data/boundaries/gyeongnam_legal_official_202609.provenance.json data/boundaries/official_boundary_verification_summary.json data/boundaries/gyeongnam_official_inventory_202609.json data/boundaries/changwon_regions_snapshot.json data/boundaries/changwon_missing_regions_202609.json data/boundaries/changwon_boundary_master_202609.json data/boundaries/changwon_official_existing181_validation.json data/boundaries/changwon_official_boundary204_validation.json data/boundaries/changwon_raw_topology_crosscheck.json data/boundaries/changwon_overlap_review_202609.geojson
git diff --cached --stat
git commit -m "Verify official Changwon boundaries and guard neighbor updates"
git push origin main
```

Render의 Events에서 새 commit의 배포가 Live인지 확인한다.
/docs의 POST /api/chat에 기존 정상 동작한 region_id와 질문을 입력한다.
답변 끝 [저장 데이터 기반 자동 비교]에 비교 지역·기간·인구·차이 또는 자료 없음 안내가 나오는지 확인한다.
이 코드를 배포해도 인접지역 등록과 월별 데이터 수집은 자동 실행되지 않는다.
현재 neighbors가 비어 있다면 미등록 안내가 나오며, 실제 인접지역 비교가 완료된 것은 아니다.

## 다음 데이터 보완 순서 (이번 적용과 별도)

1. 공식 최신 현존 법정동 코드로 누락 23개의 상태를 확인한다. 경계에 있다는 사실과 법정코드의 현존 상태 확인은 구분한다.
2. 누락 23개만 추가하는 계획을 검토하고 월별 수집·4개 지수·품질 검증을 함께 실행한다. 기존 181개와 월별 자료를 삭제/초기화하지 않는다.
3. 겹침 66쌍의 위치를 검토한다. 원본 도형 겹침은 수정된 원천 확보, 제공기관 확인 또는 근거 있는 도형 정정 기록이 필요하다. 임의로 큰 면적 허용치를 주지 않는다.
4. 해결 후 현재 Firebase master를 읽어 재검증한다. 기존 snapshot을 근거로 DB 저장하지 않는다.
5. 코드 미대응·도형 오류·겹침 0, graph_symmetric=true, self_edges=0, 고립 후보 지도 점검까지 완료한 뒤에만 적용한다.

현재 Firebase master를 읽는 재검증 명령 (DB 읽기 있음, 쓰기 없음):

```powershell
python scripts/build_neighbors.py data/boundaries/gyeongnam_legal_official_202609.geojson --source-crs EPSG:4326 --source-url "https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?dsId=30603" --source-date 2026-09 --output artifacts/changwon-live-master-boundary-check.json
```

로컬 .env에 USE_MEMORY_DB=false 및 정상 Firebase 설정이 있을 때만 실제 DB 목록을 읽는다.
아직 이 명령에 --apply를 붙이지 않는다. 이번 원본은 등록 준비 완료 상태가 아니다.
경남 전체 확대 시 자체 교차 7개와 비정상 코드 1개도 해결하고, 경남 전체 master와 대조해야 한다.

## 메타 프롬프트

공식 경계의 코드 계층·좌표계·도형 자체 유효성·도형 간 관계를 각각 검사하고, 원본 좌표와 변환 좌표로 교차검산하라. 코드 테스트 통과, 실제 자료 통과, Firebase 적용, 실서비스 확인을 별도로 기록하라. 실패를 숨기지 않고 재현 가능한 검사와 적용 차단을 제공하라.

## 메타인지와 확인 행동

'공식 파일이면 모든 공간 연산이 정상'이라는 가정을 점검한다. 개별 도형은 유효해도 서로 겹칠 수 있다. 테스트 66개 통과와 실제 경계 검증 실패가 동시에 존재할 수 있다. 운영 적용 전에 두 증거를 따로 확인한다. 특히 종료코드 2를 없애는 것보다 어떤 자료 조건 때문에 2가 나왔는지 설명할 수 있어야 한다.
