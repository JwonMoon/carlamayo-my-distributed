# 공식 Alpamayo 1.5 노트북 안내

NVIDIA가 `NVlabs/alpamayo1.5` 저장소에 넣어 둔 노트북 4개를 **추론 인스턴스 B(g6e.xlarge)에서
실행해 모델 기능을 미리 확인**하기 위한 안내다. 이 저장소의 서브모듈
`third_party/alpamayo1.5`가 바로 그 저장소이므로 별도 클론 없이 서브모듈 안의 `notebooks/`를
쓰면 된다.

근거: 업스트림 노트북 4개, `src/alpamayo1_5/load_physical_aiavdataset.py`, `pyproject.toml`,
README(하드웨어 표, FAQ)를 직접 읽고 정리했다. 실행 시간·메모리 수치 중 "예상"은 실측이
아니므로 실행 후 "실측" 열을 채우기 바란다.

---

## 1. 노트북의 공통 성격

- **전부 오프라인**이다. 시뮬레이터도, 주행도 없다.
- 입력은 NVIDIA **PhysicalAI-AV 실차 데이터셋**의 클립 하나에서 꺼낸 한 순간이다:
  카메라 4장(또는 1~2장) × 최근 4프레임 + 과거 1.6초(16스텝) 에고 이동 이력.
- 출력은 **6.4초 미래 궤적(64점, 10 Hz)** 과 Chain-of-Causation(CoC) 문장이며, 데이터셋에
  들어 있는 실제 주행 궤적(ground truth)과 그림으로 비교한다.
- 데이터는 `physical_ai_av` 패키지가 Hugging Face에서 **실행 중 스트리밍**한다. 미리 받아둘
  필요는 없지만 데이터셋 접근 승인이 없으면 로드에서 실패한다.
- Carlamayo와의 관계: Carlamayo는 이 한 번의 예측을 매초 반복하며 CARLA 카메라를 입력으로
  넣고, 예측 궤적을 PID로 실제 주행에 연결한 것이다.

---

## 2. 사전 준비 체크리스트 [B]

| 항목 | 내용 |
|---|---|
| Hugging Face 게이트 승인 ① | 모델 `nvidia/Alpamayo-1.5-10B` (가중치 약 22 GB, 첫 실행 시 다운로드) |
| Hugging Face 게이트 승인 ② | 데이터셋 `nvidia/PhysicalAI-Autonomous-Vehicles` (스트리밍용, 필수) |
| 로그인 | `hf auth login` (토큰: https://huggingface.co/settings/tokens) |
| 디스크 | HF 캐시(`~/.cache/huggingface`)에 30 GB 이상 여유 권장 |
| Python | 3.12, `uv sync --active` (Carlamayo 환경 세팅과 동일) |
| flash-attn | 빌드에 `nvcc`(CUDA Toolkit 12.x) 필요. 없으면 `uv sync --active --no-install-package flash-attn` 후 `from_pretrained(..., attn_implementation="sdpa")` |
| 노트북 실행 패키지 | `mediapy`, `ipykernel`, `ipywidgets`는 공식 `pyproject.toml`의 dev 그룹에 있음 → `uv sync --active --group dev` 또는 `uv pip install mediapy ipykernel ipywidgets jupyter` |
| 동봉 파일 | `notebooks/clip_ids.parquet`(클립 ID 목록, 예제는 774번째 사용), `notebooks/nav_demo_samples.json`(내비 지시가 붙은 클립 20개) |
| 실행 위치 | 노트북은 `clip_ids.parquet`를 상대 경로로 읽으므로 **`notebooks/` 디렉터리에서** Jupyter를 띄운다 |

---

## 3. g6e.xlarge에서 어디까지 되는가

인스턴스 사양: L40S **48 GB VRAM**, 4 vCPU, 32 GiB RAM.

공식 하드웨어 표(H100 측정):

| 설정 | VRAM |
|---|---|
| 1샘플 추론 (`num_traj_samples=1`) | ~24 GB |
| 16샘플 추론 | ~40 GB |
| 16샘플 + CFG | ~60 GB |

이를 근거로 셀 단위 예상:

| 노트북 / 셀 | 샘플 수 | 예상 VRAM | 판정 | 조치 | 예상 시간 | 실측 |
|---|---|---|---|---|---|---|
| `inference.ipynb` 모델 로드 | – | ~21 GB(가중치) | ✅ 그대로 | | 첫 회 22 GB 다운로드(수 분~수십 분) + 로드 1~2분 | |
| `inference.ipynb` 추론 | 1 | ~24 GB | ✅ 그대로 | | 수 초 | |
| `inference_vqa.ipynb` 질문 2개 | 1 | ~22 GB(텍스트 생성만, 카메라 1장) | ✅ 그대로 | | 각 수 초(최대 256토큰) | |
| `inference_cam_num.ipynb` 1/2/4캠 × 16샘플 | 16 | ~35~40 GB | ⚠️ 가능하나 여유 적음 | OOM 시 `num_traj_samples=8` | 구성당 수십 초 | |
| `inference_nav.ipynb` Part 1 | 1 | ~24 GB | ✅ 그대로 | | 수 초 | |
| `inference_nav.ipynb` Part 2 `compare_nav_conditions`(비CFG, 3조건) | 16 | ~40 GB | ⚠️ 가능하나 여유 적음 | OOM 시 8샘플 | 3조건 × 수십 초 | |
| `inference_nav.ipynb` Part 2 **CFG 셀** (`..._cfg_nav`, weight 1.5) | 16 | **~60 GB+** | ❌ 그대로는 OOM 예상 | `num_traj_samples`를 4~8로 줄이고, 앞 셀의 결과 변수를 `del` 후 `torch.cuda.empty_cache()` 실행 후 단독 실행 | 수십 초 | |
| `inference_nav.ipynb` Part 3 수동 지시, 거리 3종 | 16 | ~40 GB | ⚠️ 가능하나 여유 적음 | OOM 시 8샘플 | 지시당 수십 초 | |

OOM 대처 순서: ① 다른 노트북 커널 종료(모델이 커널마다 21 GB) → ② `num_traj_samples` 축소 →
③ 앞 셀 결과 `del` + `torch.cuda.empty_cache()` → ④ 그래도 안 되면 `max_generation_length` 축소.

RAM 32 GiB는 safetensors mmap 로드에 충분하다. 4 vCPU는 데이터 스트리밍·디코딩에서 느릴 수
있으나 정확도에는 영향이 없다.

---

## 4. 각 노트북에서 하는 일과 얻는 것

| 노트북 | 하는 일 | 입력 | 호출 API | 얻는 것 |
|---|---|---|---|---|
| `inference.ipynb` | 표준 추론 데모 | 클립 1개, 4카메라, 1샘플, 시드 42 | `sample_trajectories_from_data_with_vlm_rollout` | CoC 문장, 예측 vs GT 궤적 그림, minADE(m) |
| `inference_cam_num.ipynb` | 카메라 수 ablation | 같은 장면을 1캠(전방 wide) / 2캠(+전방 tele) / 4캠, 각 16샘플 | 같음 | 카메라 수별 CoC 문장과 궤적 분포 비교 그림 |
| `inference_nav.ipynb` | 내비 지시 조건부 예측 | 스웨덴 교차로 장면(우회전/직진 갈림), "Turn right in 30m" | `nav_utils.compare_nav_conditions`, `..._cfg_nav`(CFG), `helper.create_message(nav_text=...)` | 지시 있음/없음/반대 세 분포 BEV 그림, CFG 효과, 거리(9/18/36 m)별 회전 시작점 변화 |
| `inference_vqa.ipynb` | 시각 질의응답 | 전방 카메라 1장 × 4프레임, 질문 2개 | `helper.create_vqa_message`, `model.generate_text` | 장면 설명 답변, 교통 요소와 주행 영향 답변(텍스트) |

---

## 5. 예상 결과 (화면에 무엇이 나오는가)

- **`inference.ipynb`**: 4×4 카메라 그리드(카메라 4 × 시간 4), 한 문장짜리 CoC(예: "Slow down
  because a vehicle ahead is braking" 류), x-y 평면에 예측(파란 점선)과 GT(빨간 선)가 겹친 그림,
  마지막에 `minADE: 0.x~1.x meters` 수준의 숫자. 시드 42로 고정되어 있지만 GPU 종류·드라이버가
  다르면 값이 소폭 달라질 수 있다.
- **`inference_cam_num.ipynb`**: 세 구성의 CoC를 나란히 출력하고, 색으로 구분된 16개 궤적
  묶음 세 개가 GT 위에 겹친다. 공식 FAQ대로 **1캠만 주면 교차 교통을 보지 못해** CoC 내용과
  궤적 분포가 4캠과 눈에 띄게 달라지는 장면이 나오길 기대한다.
- **`inference_nav.ipynb`**: Part 2에서 파랑(지시대로 우회전), 빨강(지시 없음, 갈림), 초록(반대
  지시, 좌회전/직진)이 갈라지는 BEV 그림. CFG 1.5를 적용하면 파랑이 더 좁게 지시 방향으로
  몰린다. Part 3의 거리 실험에서는 "9m"일수록 곧바로 꺾이고 "36m"일수록 직진 구간이 길어진다.
- **`inference_vqa.ipynb`**: "Describe the scene." 에 대한 두세 문장 답변과, 교통 요소 질문에
  대한 신호등·차량·보행자 언급과 권장 행동이 포함된 답변.

---

## 6. Carlamayo 모드와의 대응

| 노트북 | Carlamayo 대응 | 차이 |
|---|---|---|
| `inference` | `--loop open`, `--loop closed --mode normal` | Carlamayo는 CARLA 카메라(1080p JPEG)로 매초 반복. 1샘플(`NUM_TRAJ_SAMPLES=1`) |
| `inference_nav` (비CFG) | `--mode navigation --navigation-weight 1.0` | 같은 `create_message(nav_text=...)` 경로 |
| `inference_nav` (CFG) | `--mode navigation --navigation-weight 1.5` (UI: `텍스트 \| 1.5`) | 같은 `..._cfg_nav` 경로. Carlamayo는 1샘플이라 VRAM 부담이 훨씬 작다 |
| `inference_vqa` | `--mode vqa` | 같은 `generate_text`. **궤적을 만들지 않으므로 Carlamayo는 차량을 정지**시킨다 |
| `inference_cam_num` | (대응 없음) | Carlamayo는 4카메라 고정. 카메라 수 실험은 노트북에서만 |

---

## 7. 실행 명령 [B]

```bash
cd ~/carlamayo
git submodule update --init third_party/alpamayo1.5
source a_venv/bin/activate
uv pip install mediapy ipykernel ipywidgets jupyter
hf auth login                                   # 최초 1회

cd third_party/alpamayo1.5/notebooks
jupyter notebook --no-browser --port 8888
```

로컬 PC에서 터널을 열고 브라우저로 접속한다:

```bash
ssh -N -L 8888:localhost:8888 ubuntu@<B의 접속 주소>
# 브라우저: http://localhost:8888/?token=...
```

먼저 `inference.ipynb`를 끝까지 돌려 모델 다운로드·데이터 스트리밍·GPU를 확인한 뒤,
`inference_vqa` → `inference_nav`(CFG 셀은 샘플 수 축소) → `inference_cam_num` 순서를 권한다.
노트북 하나를 끝내면 커널을 종료해 VRAM을 비운 뒤 다음 것을 연다.
