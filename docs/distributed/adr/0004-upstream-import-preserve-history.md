# 0004. 업스트림은 git 히스토리를 보존해 가져온다

상태: 채택      날짜: 2026-09-30

## 상황
이 저장소는 빈 상태로 시작했고, `aveeslab/Carlamayo`(커밋 `e6372ea`, 99개 커밋, 서브모듈 4개)를
가져와 커스텀 버전을 관리해야 한다.

## 후보
- (a) `git fetch upstream` 후 그 커밋 위에 브랜치를 만들어 **히스토리 전체를 보존**하고 `upstream` 리모트를 둔다.
- (b) HEAD 파일만 복사해 스냅샷 1커밋으로 시작한다.
- (c) `git subtree add`로 하위 폴더에 넣는다.

## 결정
(a).

## 이유
- 업스트림이 계속 갱신되므로(`Carlamayo-1.5`, `Carlamayo-2`, `CARLA0.10.0-Alpamayo` 브랜치가
  활발함) `git fetch upstream && git merge upstream/main`으로 따라갈 수 있어야 한다. 히스토리가
  같아야 merge가 충돌 최소로 된다.
- `git blame`/`git log`로 "이 줄이 업스트림 것인지 우리가 바꾼 것인지"를 바로 알 수 있다.
  변경 기록 문서([changes-from-upstream.md](../changes-from-upstream.md))의 근거가 된다.
- `.gitmodules`의 서브모듈 URL이 절대 경로라 그대로 유지된다. 서브모듈은 B(추론 호스트)에서만
  초기화하면 된다.

## 탈락 이유
- (b) 스냅샷: 단순하지만 이후 업스트림 변경을 수동으로 옮겨야 한다.
- (c) subtree: 코드가 하위 폴더로 들어가 import 경로와 문서의 상대 경로가 전부 바뀐다.

## 결과
- 브랜치 `claude/nice-planck-dec7fo`가 `upstream/main`(`e6372ea`)에서 시작한다.
- 리모트: `origin` = 이 저장소, `upstream` = `https://github.com/aveeslab/Carlamayo.git`.
- 동기화 절차는 README에 적는다.
