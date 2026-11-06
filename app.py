"""DualSense Studio window, alarm, and the bridge to the page."""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import webview

from audio_io import AudioIO
from dualsense import DualSense
from i18n import get_strings


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def _settings_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "settings.json"
    return Path(__file__).resolve().parent / "settings.json"


ROOT = _bundle_root()
SETTINGS = _settings_path()


def _load_settings():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"lang": "en"}


def _save_settings(data):
    SETTINGS.write_text(json.dumps(data), encoding="utf-8")


class Studio:
    def __init__(self):
        self.pad = DualSense()
        self.audio = AudioIO()
        self.settings = _load_settings()
        self._lock = threading.Lock()
        self._alarm = {
            "armed": False,
            "firing": False,
            "deadline": 0.0,
            "snooze": 60,
            "channels": {},
            "color": [220, 48, 24],
            "player": 0x04,
            "triggerMode": "feedback",
            "trigger": {"position": 0, "strength": 8},
            "rumble": [90, 60],
            "tone": 880,
        }
        self._closed = False

    def start(self):
        self.pad.start()
        self.audio.start()
        threading.Thread(target=self._alarm_loop, name="dualsense-alarm", daemon=True).start()

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        with self._lock:
            self._alarm["armed"] = False
            self._alarm["firing"] = False
        self.audio.stop()
        self.pad.stop()

    def get_strings(self, lang):
        return get_strings(lang)

    def get_settings(self):
        return self.settings

    def set_language(self, lang):
        lang = "fa" if lang == "fa" else "en"
        self.settings["lang"] = lang
        _save_settings(self.settings)
        return {"lang": lang}

    def get_state(self):
        state = self.pad.snapshot()
        state["audio"] = self.audio.snapshot()
        state["lang"] = self.settings.get("lang", "en")
        with self._lock:
            alarm = dict(self._alarm)
        remaining = 0
        if alarm["armed"] and not alarm["firing"]:
            remaining = max(0, int(alarm["deadline"] - time.time()))
        state["alarm"] = {
            "armed": alarm["armed"],
            "firing": alarm["firing"],
            "remaining": remaining,
        }
        return state

    def reset_drift(self):
        self.pad.reset_drift()
        return {"ok": True}

    def set_rumble(self, left, right):
        try:
            self.pad.set_rumble(left, right)
            return {"ok": True}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def pulse_rumble(self, left, right, duration_ms):
        try:
            self.pad.set_rumble(left, right)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

        def stop_later():
            time.sleep(max(40, min(4000, int(duration_ms))) / 1000)
            try:
                self.pad.set_rumble(0, 0)
            except OSError:
                pass

        threading.Thread(target=stop_later, daemon=True).start()
        return {"ok": True}

    def stop_rumble(self):
        return self.set_rumble(0, 0)

    def set_trigger(self, side, mode, params):
        try:
            return self.pad.set_trigger(side, mode, params or {})
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def set_triggers(self, left, right):
        try:
            return self.pad.set_triggers(left or {}, right or {})
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def set_light(self, red, green, blue, brightness, player, mute_led, command):
        try:
            self.pad.set_light(red, green, blue, brightness, player, mute_led, command)
            return {"ok": True}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def set_audio(self, speaker, headphone, mic, preamp, path, mic_muted):
        try:
            self.pad.set_audio(speaker, headphone, mic, preamp, path, mic_muted)
            return {"ok": True}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def play_tone(self, frequency, duration_ms):
        try:
            self.audio.play_tone(frequency, duration_ms)
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def reconnect(self):
        self.pad.reconnect()
        self.audio.refresh()
        return {"ok": True}

    def release_all(self):
        with self._lock:
            self._alarm["armed"] = False
            self._alarm["firing"] = False
        self.audio.stop_tone()
        self.pad.release_all()
        return {"ok": True}

    def arm_alarm(self, spec):
        spec = spec or {}
        kind = spec.get("kind", "countdown")
        now = datetime.now()
        if kind == "clock":
            hour = int(spec.get("hour", now.hour))
            minute = int(spec.get("minute", now.minute))
            target = now.replace(hour=hour % 24, minute=minute % 60, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            deadline = target.timestamp()
        else:
            deadline = time.time() + max(1, int(spec.get("seconds", 10)))
        channels = spec.get("channels") or {}
        with self._lock:
            self._alarm.update({
                "armed": True,
                "firing": False,
                "deadline": deadline,
                "snooze": max(5, int(spec.get("snooze", 60))),
                "channels": channels,
                "color": spec.get("color") or [220, 48, 24],
                "player": int(spec.get("player", 0x04)),
                "triggerMode": spec.get("triggerMode") or "feedback",
                "trigger": spec.get("trigger") or {"position": 0, "strength": 8},
                "rumble": spec.get("rumble") or [90, 60],
                "tone": int(spec.get("tone", 880)),
            })
        return {"ok": True}

    def snooze_alarm(self):
        with self._lock:
            snooze = self._alarm.get("snooze", 60)
            self._alarm["firing"] = False
            self._alarm["armed"] = True
            self._alarm["deadline"] = time.time() + snooze
            channels = dict(self._alarm.get("channels") or {})
        self._silence(channels)
        return {"ok": True}

    def stop_alarm(self):
        with self._lock:
            channels = dict(self._alarm.get("channels") or {})
            self._alarm["armed"] = False
            self._alarm["firing"] = False
        self._silence(channels)
        return {"ok": True}

    def _silence(self, channels):
        self.audio.stop_tone()
        try:
            if channels.get("rumbleL") or channels.get("rumbleR"):
                self.pad.set_rumble(0, 0)
            if channels.get("left") and channels.get("right"):
                self.pad.set_trigger("both", "off", {})
            elif channels.get("left"):
                self.pad.set_trigger("left", "off", {})
            elif channels.get("right"):
                self.pad.set_trigger("right", "off", {})
            if channels.get("light") or channels.get("player"):
                self.pad.set_light(0, 0, 0, 0, 0, 0, "release")
        except OSError:
            pass

    def _alarm_loop(self):
        while not self._closed:
            time.sleep(0.2)
            with self._lock:
                alarm = dict(self._alarm)
                channels = dict(alarm.get("channels") or {})
            if not alarm["armed"]:
                continue
            if not alarm["firing"]:
                if time.time() >= alarm["deadline"]:
                    with self._lock:
                        self._alarm["firing"] = True
                continue
            self._ring(channels, alarm)
            time.sleep(0.45)
            if channels.get("rumbleL") or channels.get("rumbleR"):
                try:
                    self.pad.set_rumble(0, 0)
                except OSError:
                    pass
            time.sleep(0.25)

    def _ring(self, channels, alarm):
        try:
            if channels.get("rumbleL") or channels.get("rumbleR"):
                left, right = alarm.get("rumble") or [90, 60]
                self.pad.set_rumble(left if channels.get("rumbleL") else 0, right if channels.get("rumbleR") else 0)
            if channels.get("left") or channels.get("right"):
                side = "both" if channels.get("left") and channels.get("right") else ("left" if channels.get("left") else "right")
                self.pad.set_trigger(side, alarm.get("triggerMode") or "feedback", alarm.get("trigger") or {})
            if channels.get("light") or channels.get("player"):
                color = alarm.get("color") or [220, 48, 24]
                player = alarm.get("player", 0x04) if channels.get("player") else 0
                if channels.get("light"):
                    self.pad.set_light(color[0], color[1], color[2], 255, player, 0, "color")
                else:
                    self.pad.set_light(0, 0, 0, 0, player, 0, "color")
            if channels.get("speaker"):
                self.audio.play_tone(alarm.get("tone") or 880, 280)
        except (OSError, RuntimeError):
            pass


def main():
    studio = Studio()
    studio.start()
    api = studio
    window = webview.create_window(
        "DualSense Studio",
        (ROOT / "ui" / "index.html").as_uri(),
        js_api=api,
        width=1240,
        height=820,
        min_size=(420, 560),
        background_color="#0c0d12",
    )

    def on_closed():
        studio.shutdown()

    window.events.closed += on_closed
    webview.start()
    studio.shutdown()


if __name__ == "__main__":
    main()
