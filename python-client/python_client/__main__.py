import argparse
from faster_whisper import WhisperModel
import sounddevice
import webrtcvad

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=12765)
    args = parser.parse_args()

    print("hello from notely-stt", args.port)

if __name__ == "__main__":
    main()
