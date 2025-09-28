import sys
import json
import os
import threading
import queue
import signal
from pathlib import Path
from typing import Optional

from .stt import STTEngine

# --------- STDIN 명령 수신 스레드 ----------
class StdinCommandListener(threading.Thread):
    def __init__(self, q: queue.Queue):
        super().__init__(daemon=True)
        self.q = q

    def run(self):
        for line in sys.stdin:
            cmd = line.strip().upper()
            if cmd == "STOP":
                self.q.put({"type": "STOP"})
                break


def print_event(event: dict):
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# --------- 스프링 서버 업로드(최종 전체 자막) ----------
def post_full_transcript(transcript_text: str) -> None:
    import requests  

    base = os.getenv("SPRING_SERVER_URL", "http://localhost:8080")
    endpoint = os.getenv("SPRING_TRANSCRIPT_PATH", "/api/stt/transcripts")
    url = f"{base.rstrip('/')}{endpoint}"

    payload = {
        "sessionId": os.getenv("SESSION_ID", "default-session"),
        "text": transcript_text,
    }

    try:
        resp = requests.post(url, json=payload, timeout=5)
        print_event({
            "type": "upload_result",
            "status": resp.status_code,
            "url": url
        })
    except Exception as e:
        print_event({
            "type": "upload_error",
            "error": repr(e),
            "url": url
        })


# --------- 메인 ---------
def main():
    model_name = os.getenv("NOTELY_STT_MODEL", "base")
    device = os.getenv("NOTELY_STT_DEVICE", "cpu")
    compute_type = os.getenv("NOTELY_STT_COMPUTE", "int8")  
    cache_dir = Path(os.getenv("NOTELY_STT_CACHE", str(Path.home() / ".cache" / "notely_stt_models")))
    cache_dir.mkdir(parents=True, exist_ok=True)

    # STT 엔진 준비
    engine = STTEngine(
        model_name=model_name,
        device=device,
        compute_type=compute_type,
        download_root=cache_dir,
        language=None 
    )

    stop_flag = threading.Event()
    cmd_queue: queue.Queue = queue.Queue()

    def handle_sigint(signum, frame):
        cmd_queue.put({"type": "STOP"})
    signal.signal(signal.SIGINT, handle_sigint)

    # STDIN 명령 수신 스레드
    stdin_listener = StdinCommandListener(cmd_queue)
    stdin_listener.start()

    cumulative_text_parts = []

    def on_partial(text: str):
        if not text:
            return
        cumulative_text_parts.append(text)
        print_event({"type": "partial", "text": text})

    engine.start(on_partial=on_partial)

    print_event({"type": "ready", "model": model_name, "device": device, "compute": compute_type})

    # 메인 루프: STOP 대기
    while True:
        try:
            msg = cmd_queue.get(timeout=0.25)
        except queue.Empty:
            if not engine.is_running():
                break
            continue

        if msg.get("type") == "STOP":
            break

    # 정지 처리
    engine.stop()

    # 전체 자막 생성 및 업로드
    full_text = "\n".join(cumulative_text_parts).strip()
    print_event({"type": "final_text", "text": full_text})

    # 스프링 서버 업로드
    post_full_transcript(full_text)

    print_event({"type": "bye"})


if __name__ == "__main__":
    main()
