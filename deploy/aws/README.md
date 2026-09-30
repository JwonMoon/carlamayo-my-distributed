# AWS 배포 메모 (두 인스턴스)

| 역할 | 인스턴스 | 내부 IP | GPU | 사용 포트 |
|---|---|---|---|---|
| A. sim host | g5.2xlarge | `172.31.38.219` | A10G 24 GB | CARLA 2000~2002, TM 8000 (모두 localhost), DCV 8443 |
| B. inference host | g6e.xlarge | `172.31.20.213` | L40S 48 GB | gRPC **50051** |

## AMI / 드라이버

- 두 인스턴스 모두 NVIDIA 드라이버가 설치된 이미지(Deep Learning AMI 또는 Ubuntu 22.04 +
  드라이버). `nvidia-smi`가 동작해야 한다.
- A: CARLA 0.9.16(UE4)은 **Vulkan** 런타임이 필요하다(`sudo apt-get install -y libvulkan1`).
  NICE DCV 가상 세션이 pygame 창을 표시한다.
- B: CUDA Toolkit 12.x(`nvcc`)가 있으면 flash-attn을 빌드한다. 없으면 SDPA 폴백(공식 README).

## 보안그룹

| 대상 | 인바운드 | 소스 | 용도 |
|---|---|---|---|
| A | 22 | 운영자 IP | SSH |
| A | 8443 | 운영자 IP | NICE DCV |
| B | 22 | 운영자 IP, **A의 SG** | SSH, `rsync`(데이터셋·프로파일 복사) |
| B | 50051 | **A의 SG** | gRPC 추론 |

### 규칙을 넣는 두 가지 방법

`launch-wizard-xx`처럼 자동 생성된 B의 그룹은 보통 사무실 IP만 허용하므로 A→B 접속이
"connection refused"가 아니라 **응답 없이 멈춘다**(패킷이 버려짐). 해결은 둘 중 하나:

1. **B에 A의 보안그룹을 추가로 연결**: 인스턴스 → 작업 → 보안 → 보안 그룹 변경 → A의 그룹
   (`vs-advancedsw-adas-ec2`: 172.31.0.0/16 전체 TCP 허용) 추가, 기존 그룹 유지. 필요한 권한
   `ec2:ModifyInstanceAttribute`.
2. **B의 그룹에 규칙 추가**: 보안 그룹 → B의 그룹 → 인바운드 규칙 편집 → TCP 22, TCP 50051,
   원본 = A의 보안그룹 ID. 필요한 권한 `ec2:AuthorizeSecurityGroupIngress`.

계정에 권한이 없으면(콘솔에 `ec2:DescribeSecurityGroupRules 권한이 없습니다`) 관리자에게
아래처럼 요청한다:

> 시뮬레이터 인스턴스 A(172.31.38.219, sg-A)에서 추론 인스턴스 B(172.31.20.213, sg-B)로
> 내부망 SSH(22)·gRPC(50051) 접속이 필요합니다. B의 보안그룹이 사무실 IP만 허용해 막혀 있습니다.
> (1) B에 sg-A를 추가 연결하거나, (2) sg-B 인바운드에 TCP 22·50051(원본 sg-A)을 추가해
> 주시거나, (3) 제 IAM 사용자에 `ec2:DescribeSecurityGroupRules`, `ec2:DescribeSecurityGroups`,
> `ec2:AuthorizeSecurityGroupIngress`, `ec2:ModifyInstanceAttribute` 권한을 부여해 주세요.
> 모두 VPC 내부 트래픽이며 외부 개방은 없습니다.

CARLA 포트(2000~2002, 8000)는 어디에도 열지 않는다. 서버는 `--host 172.31.20.213`(사설 IP)으로
바인드한다. gRPC는 평문이므로 VPC 밖으로 노출하지 않는다.

## 설치

```bash
# [A]
git clone https://github.com/jwonmoon/carlamayo-my-distributed.git ~/carlamayo
~/carlamayo/deploy/scripts/setup-sim-host.sh

# [B]
git clone https://github.com/jwonmoon/carlamayo-my-distributed.git ~/carlamayo
~/carlamayo/deploy/scripts/setup-inference-host.sh
hf auth login
```

## 서버를 systemd 서비스로

```bash
# [B]
sudo cp ~/carlamayo/deploy/systemd/alpamayo-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now alpamayo-server
journalctl -u alpamayo-server -f
```

유닛 파일의 `User=`, `WorkingDirectory=`, `ExecStart=`의 경로와 `--host`를 환경에 맞게 고친다.
모델 로드 + 워밍업이 수 분 걸리므로 `TimeoutStartSec=900`이다.

## 네트워크 경로 먼저 확인하기 (모델 없이)

```bash
# [B]  GPU 없이 가짜 모델로 서버 기동
python alpamayo_server.py --fake --host 172.31.20.213 --port 50051
# [A]
nc -zv 172.31.20.213 50051
```

가짜 서버는 버전 `fake`를 광고하므로 `carlamayo.py --version 1.5`는 버전 불일치로 종료한다
(의도된 가드). 대신 아래 스니펫으로 핸드셰이크와 왕복(RTT, 요청 크기)을 검증한다:

```bash
# [A]
python - <<'EOF'
import numpy as np
from module import config as cfg
from module.remote.client import RemoteAlpamayoAdapter
r = RemoteAlpamayoAdapter("172.31.20.213:50051", expected_version="fake"); r.load_model()
img = np.zeros((4, cfg.NUM_FRAMES, cfg.IMG_HEIGHT, cfg.IMG_WIDTH, 3), np.uint8)
d = r.prepare_model_input(img, np.zeros((16, 3), np.float32), np.tile(np.eye(3, dtype=np.float32), (16, 1, 1)), 0)
pred, extra = r.run_inference(None, None, d)
print("OK", pred.shape, f"rtt={extra['rtt_sec']:.3f}s request={extra['request_bytes']/1e6:.1f}MB")
EOF
```

## 비용

실험이 없을 때는 두 인스턴스를 stop 한다. open-loop만 돌릴 때는 A만 stop 하면 된다.
