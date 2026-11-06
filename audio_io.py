"""DualSense speaker tone and microphone meter through WASAPI."""

from __future__ import annotations

import threading

try:
    import numpy as np
    import sounddevice as sd
except Exception:  # noqa: BLE001
    np = None
    sd = None


class AudioIO:
    def __init__(self):
        self._lock = threading.Lock()
        self.output_index = None
        self.input_index = None
        self.output_name = ""
        self.input_name = ""
        self.output_channels = 0
        self._inputs = []
        self._outputs = []
        self.error = ""
        self.level = 0.0
        self.frames = 0
        self.frames = 0
        self._stream = None
        self._available = sd is not None and np is not None

    def start(self):
        if not self._available:
            self.error = "sounddevice unavailable"
            return
        self.refresh()
        self._open_mic()

    def stop(self):
        self.stop_tone()
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def refresh(self):
        if not self._available:
            return
        try:
            hostapis = sd.query_hostapis()
            wasapi = next((index for index, api in enumerate(hostapis) if "WASAPI" in api["name"].upper()), None)
            kernel = next((index for index, api in enumerate(hostapis) if "WDM-KS" in api["name"].upper()), None)
            devices = sd.query_devices()
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            return
        self._inputs = []
        self._outputs = []
        self.output_index = None
        self.input_index = None
        outputs = []
        inputs = []
        for index, device in enumerate(devices):
            name = device["name"].lower()
            if "dualsense" not in name:
                continue
            if device["max_output_channels"] > 0:
                outputs.append((index, device))
            if device["max_input_channels"] > 0:
                inputs.append((index, device))
        outputs.sort(key=lambda item: 0 if item[1]["hostapi"] == wasapi else 1 if item[1]["hostapi"] == kernel else 2)
        inputs.sort(key=lambda item: 0 if item[1]["hostapi"] == kernel else 1 if item[1]["hostapi"] == wasapi else 2)
        self._outputs = [index for index, _device in outputs]
        self._inputs = [index for index, _device in inputs]
        if self._outputs:
            self.output_index = self._outputs[0]
            self.output_name = devices[self.output_index]["name"]
            self.output_channels = int(devices[self.output_index]["max_output_channels"])
        if self._inputs:
            self.input_index = self._inputs[0]
            self.input_name = devices[self.input_index]["name"]
        if self.output_index is None and self.input_index is None:
            self.error = "DualSense audio endpoint not found"
        else:
            self.error = ""

    def snapshot(self):
        return {
            "available": self._available and (self.output_index is not None or self.input_index is not None),
            "outputName": self.output_name,
            "inputName": self.input_name,
            "channels": self.output_channels,
            "level": round(self.level, 4),
            "frames": self.frames,
            "error": self.error,
        }

    def play_tone(self, frequency, duration_ms):
        if not self._available or self.output_index is None:
            self.refresh()
        if not self._available or self.output_index is None:
            raise RuntimeError(self.error or "no speaker")
        frequency = max(40, min(4000, int(frequency)))
        duration_ms = max(40, min(4000, int(duration_ms)))
        rate = 48000
        count = int(rate * duration_ms / 1000)
        time_axis = np.linspace(0, duration_ms / 1000, count, endpoint=False)
        wave = (0.22 * np.sin(2 * np.pi * frequency * time_axis)).astype(np.float32)
        channels = min(self.output_channels or 2, 4)
        buffer = np.zeros((count, channels), dtype=np.float32)
        if channels >= 4:
            buffer[:, 2] = wave
            buffer[:, 3] = wave
        else:
            buffer[:, :] = wave[:, None]
        sd.play(buffer, rate, device=self.output_index)

    def stop_tone(self):
        if sd is None:
            return
        try:
            sd.stop()
        except Exception:
            pass

    def _open_mic(self):
        if self.input_index is None:
            return
        if self._stream is not None:
            return

        def callback(indata, frames, time_info, status):
            if status:
                self.error = str(status)
            rms = float(np.sqrt(np.mean(np.square(indata))))
            with self._lock:
                self.frames += frames
                self.level = min(1.0, rms * 12.0)

        last = "no microphone"
        for index in self._inputs:
            try:
                info = sd.query_devices(index)
                channels = max(1, min(2, int(info["max_input_channels"])))
                stream = sd.InputStream(
                    device=index,
                    channels=channels,
                    samplerate=int(info["default_samplerate"] or 48000),
                    callback=callback,
                    blocksize=1024,
                )
                stream.start()
                self._stream = stream
                self.input_index = index
                self.input_name = info["name"]
                self.error = ""
                return
            except Exception as exc:  # noqa: BLE001
                last = str(exc)
        self.error = last
        self._stream = None
