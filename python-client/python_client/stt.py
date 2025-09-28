import threading
import queue
import time
from typing import Callable, Optional, List

import numpy as np
import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel


class STTEngine:

    def __init__(
        self,
        model_name: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        download_root=None,
        language: Optional[str] = None,
        sample_rate: int = 16000,
        vad_aggressiveness: int = 2,
        silence_ms_to_end: int = 600,
    ):
        self.sample_rate = sample_rate
        self.frame_ms = 20
        self.frame_samples = int(self.sample_rate * self.frame_ms / 1000)  # 320 at 16k
        self.channels = 1

        self.vad = webrtcvad.Vad(vad_aggressiveness)
        self.max_silence_frames = int(silence_ms_to_end / self.frame_ms)  # 600ms -> 30 frames

        # faster-whisper 모델 준비(없으면 자동 다운로드)
        self.model = WhisperModel(
            model_size_or_path=model_name,
            device=device,
            compute_type=compute_type,
            download_root=str(download_root) if download_root else None,
        )
        self.language = language

        # 쓰레딩/큐
        self._audio_q: queue.Queue = queue.Queue(maxsize=100)  # 프레임 큐
        self._run_flag = threading.Event()
        self._run_flag.clear()
        self._worker_t: Optional[threading.Thread] = None
        self._on_partial: Optional[Callable[[str], None]] = None

        self._stream: Optional[sd.InputStream] = None

    # ---------- 오디오 콜백 ----------
    def _sd_callback(self, indata, frames, time_info, status):
        if status:
            # 상태 메시지는 무시 가능(언더런 등)
            pass

        # 입력은 float32(-1..1). int16로 변환 후 VAD용 프레임으로 쪼개기
        mono = indata[:, 0] if indata.ndim > 1 else indata
        pcm16 = np.clip(mono * 32768.0, -32768, 32767).astype(np.int16)

        # 20ms 단위로 큐에 넣기
        i = 0
        total = len(pcm16)
        frame_len = self.frame_samples
        while i + frame_len <= total:
            frame = pcm16[i:i + frame_len].tobytes()
            try:
                self._audio_q.put_nowait(frame)
            except queue.Full:
                # 프레임 드랍(밀릴 경우)
                pass
            i += frame_len

    # ---------- 워커: VAD 세그먼트 → Whisper 추론 ----------
    def _worker(self):
        segment_frames: List[bytes] = []
        silence_count = 0
        in_speech = False

        def flush_segment():
            # 세그먼트가 있을 때 whisper에 전달
            nonlocal segment_frames
            if not segment_frames:
                return

            # bytes→int16→float32(-1..1)
            pcm = b"".join(segment_frames)
            audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

            try:
                segments, info = self.model.transcribe(
                    audio=audio,
                    language=self.language,  # None=auto
                    vad_filter=False,        # 이미 webrtcvad로 자른 상태
                    beam_size=1,
                    best_of=1,
                )
                text_chunks = [seg.text for seg in segments]  # type: ignore
                text = " ".join(t.strip() for t in text_chunks).strip()
                if self._on_partial:
                    self._on_partial(text)
            except Exception as e:
                if self._on_partial:
                    self._on_partial(f"[STT error: {repr(e)}]")

            segment_frames = []

        while self._run_flag.is_set():
            try:
                frame = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue

            is_speech = False
            try:
                is_speech = self.vad.is_speech(frame, self.sample_rate)
            except Exception:
                # VAD 예외는 무시(드문 샘플 길이 오차 등)
                pass

            if is_speech:
                in_speech = True
                silence_count = 0
                segment_frames.append(frame)
            else:
                if in_speech:
                    silence_count += 1
                    segment_frames.append(frame)

                    # 일정 시간 침묵이면 세그먼트 종료
                    if silence_count >= self.max_silence_frames:
                        flush_segment()
                        in_speech = False
                        silence_count = 0
                        segment_frames = []
                else:
                    # 비음성 지속
                    pass

        # 종료 직전 남은 세그먼트 처리
        if segment_frames:
            in_speech = False
            silence_count = 0
            # 짧은 꼬리라도 플러시
            try:
                # 재사용
                pcm = b"".join(segment_frames)
                audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
                segments, info = self.model.transcribe(
                    audio=audio,
                    language=self.language,
                    vad_filter=False,
                    beam_size=1,
                    best_of=1,
                )
                text = " ".join(seg.text for seg in segments)  # type: ignore
                if self._on_partial:
                    self._on_partial(text.strip())
            except Exception:
                pass

    # ---------- 퍼블릭 API ----------
    def start(self, on_partial: Callable[[str], None]):
        if self._run_flag.is_set():
            return
        self._on_partial = on_partial
        # 오디오 스트림 시작
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.frame_samples,  # 20ms
            callback=self._sd_callback,
        )
        self._stream.start()

        # 워커 스레드 시작
        self._run_flag.set()
        self._worker_t = threading.Thread(target=self._worker, daemon=True)
        self._worker_t.start()

    def stop(self):
        self._run_flag.clear()
        # 스트림 먼저 정지
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass

        # 워커 종료 대기
        if self._worker_t and self._worker_t.is_alive():
            self._worker_t.join(timeout=2.0)

    def is_running(self) -> bool:
        return self._run_flag.is_set()
