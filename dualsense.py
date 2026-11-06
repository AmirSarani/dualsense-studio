"""USB DualSense HID: full input decode and full output report."""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
DIGCF_PRESENT = 0x2
DIGCF_DEVICEINTERFACE = 0x10
ERROR_IO_PENDING = 997
INVALID = wintypes.HANDLE(-1).value

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.ReadFile.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
]
kernel32.ReadFile.restype = wintypes.BOOL
kernel32.WriteFile.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
]
kernel32.WriteFile.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
kernel32.ResetEvent.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.GetOverlappedResult.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
]
kernel32.GetOverlappedResult.restype = wintypes.BOOL
kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.CancelIoEx.restype = wintypes.BOOL
hid.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
hid.HidD_GetFeature.restype = wintypes.BOOL
hid.HidD_GetProductString.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
hid.HidD_GetProductString.restype = wintypes.BOOL
hid.HidD_GetManufacturerString.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
hid.HidD_GetManufacturerString.restype = wintypes.BOOL


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


GUID_HID = GUID(
    0x4D1E55B2, 0xF16F, 0x11CF,
    (ctypes.c_ubyte * 8)(0x88, 0xCB, 0x00, 0x11, 0x11, 0x00, 0x00, 0x30),
)

setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
]
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

BUTTONS = [
    (0, 0x10, "square"),
    (0, 0x20, "cross"),
    (0, 0x40, "circle"),
    (0, 0x80, "triangle"),
    (1, 0x01, "l1"),
    (1, 0x02, "r1"),
    (1, 0x04, "l2"),
    (1, 0x08, "r2"),
    (1, 0x10, "create"),
    (1, 0x20, "options"),
    (1, 0x40, "l3"),
    (1, 0x80, "r3"),
    (2, 0x01, "ps"),
    (2, 0x02, "touchpad"),
    (2, 0x04, "mute"),
]

HAT = ["n", "ne", "e", "se", "s", "sw", "w", "nw", "center"]

CHARGE = {
    0x0: "discharging",
    0x1: "charging",
    0x2: "full",
    0xA: "voltage_temp",
    0xB: "temp_error",
    0xF: "charge_error",
}


def hid_paths():
    found = []
    handle = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(GUID_HID), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if not handle or handle == INVALID:
        return found
    try:
        index = 0
        while True:
            data = SP_DEVICE_INTERFACE_DATA()
            data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            ok = setupapi.SetupDiEnumDeviceInterfaces(
                handle, None, ctypes.byref(GUID_HID), index, ctypes.byref(data)
            )
            if not ok:
                break
            need = wintypes.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                handle, ctypes.byref(data), None, 0, ctypes.byref(need), None
            )
            buf = ctypes.create_string_buffer(max(need.value, 8))
            ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0] = 8
            if setupapi.SetupDiGetDeviceInterfaceDetailW(
                handle, ctypes.byref(data), buf, need, ctypes.byref(need), None
            ):
                found.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
            index += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(handle)
    return found


def find_dualsense_path():
    for path in hid_paths():
        upper = path.upper()
        if "VID_054C&PID_0CE6" in upper:
            return path
    return None


def _open(path, access, flags=0):
    handle = kernel32.CreateFileW(
        path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, flags, None
    )
    if handle == INVALID:
        raise OSError(ctypes.get_last_error())
    return handle


def _hid_string(fn, handle):
    buf = ctypes.create_unicode_buffer(128)
    if not fn(handle, buf, ctypes.sizeof(buf)):
        return ""
    return buf.value


def _feature(handle, report_id, size):
    buf = ctypes.create_string_buffer(size)
    buf[0] = report_id
    if not hid.HidD_GetFeature(handle, buf, size):
        return None
    return bytes(buf)


def _i16(buf, offset):
    return int.from_bytes(buf[offset:offset + 2], "little", signed=True)


def _u32(buf, offset):
    return int.from_bytes(buf[offset:offset + 4], "little")


def _clamp(value, lo, hi):
    return max(lo, min(hi, int(value)))


def effect_off():
    block = bytearray(11)
    block[0] = 0x05
    return block


def _pack_zones(strengths):
    force = 0
    active = 0
    for index, raw in enumerate(strengths):
        strength = _clamp(raw, 0, 8)
        if strength > 0:
            force |= ((strength - 1) & 0x07) << (3 * index)
            active |= 1 << index
    return force, active


def _write_zones(mode, strengths, frequency=0):
    force, active = _pack_zones(strengths)
    block = bytearray(11)
    if active == 0:
        return effect_off()
    block[0] = mode
    block[1] = active & 0xFF
    block[2] = (active >> 8) & 0xFF
    block[3] = force & 0xFF
    block[4] = (force >> 8) & 0xFF
    block[5] = (force >> 16) & 0xFF
    block[6] = (force >> 24) & 0xFF
    block[9] = frequency & 0xFF
    return block


def encode_effect(mode, params):
    """Return (11-byte block, applied params). Raises ValueError on a bad mode."""
    mode = (mode or "off").lower()
    params = params or {}
    if mode == "off":
        return effect_off(), {"mode": "off"}
    if mode == "feedback":
        position = _clamp(params.get("position", 0), 0, 9)
        strength = _clamp(params.get("strength", 0), 0, 8)
        zones = [0] * 10
        for index in range(position, 10):
            zones[index] = strength
        block = _write_zones(0x21, zones)
        applied = {"mode": mode, "position": position, "strength": strength, "zones": zones}
        return _as_off(block, applied)
    if mode == "zones":
        zones = [_clamp(v, 0, 8) for v in (params.get("zones") or [0] * 10)[:10]]
        zones += [0] * (10 - len(zones))
        block = _write_zones(0x21, zones)
        return _as_off(block, {"mode": mode, "zones": zones})
    if mode == "slope":
        start = _clamp(params.get("start", 0), 0, 8)
        end = _clamp(params.get("end", 9), start + 1, 9)
        start_s = _clamp(params.get("startStrength", 1), 1, 8)
        end_s = _clamp(params.get("endStrength", 8), 1, 8)
        zones = [0] * 10
        span = end - start
        for index in range(start, 10):
            if index <= end:
                zones[index] = int(round(start_s + (end_s - start_s) * (index - start) / span))
            else:
                zones[index] = end_s
            zones[index] = _clamp(zones[index], 1, 8)
        block = _write_zones(0x21, zones)
        return _as_off(block, {
            "mode": mode, "start": start, "end": end,
            "startStrength": start_s, "endStrength": end_s, "zones": zones,
        })
    if mode == "weapon":
        start = _clamp(params.get("start", 2), 2, 7)
        end = _clamp(params.get("end", 8), start + 1, 8)
        strength = _clamp(params.get("strength", 1), 0, 8)
        if strength <= 0:
            return effect_off(), {"mode": "off"}
        zones = (1 << start) | (1 << end)
        block = bytearray(11)
        block[0] = 0x25
        block[1] = zones & 0xFF
        block[2] = (zones >> 8) & 0xFF
        block[3] = strength - 1
        return block, {"mode": mode, "start": start, "end": end, "strength": strength}
    if mode == "bow":
        start = _clamp(params.get("start", 0), 0, 8)
        end = _clamp(params.get("end", 4), start + 1, 8)
        strength = _clamp(params.get("strength", 6), 0, 8)
        snap = _clamp(params.get("snapForce", 4), 0, 8)
        if strength <= 0 or snap <= 0:
            return effect_off(), {"mode": "off"}
        force = ((strength - 1) & 0x07) | (((snap - 1) & 0x07) << 3)
        return _span_block(0x22, start, end, force), {
            "mode": mode, "start": start, "end": end, "strength": strength, "snapForce": snap,
        }
    if mode == "galloping":
        start = _clamp(params.get("start", 0), 0, 8)
        end = _clamp(params.get("end", 9), start + 1, 9)
        first = _clamp(params.get("firstFoot", 2), 0, 6)
        second = _clamp(params.get("secondFoot", 4), first + 1, 7)
        frequency = _clamp(params.get("frequency", 8), 0, 255)
        if frequency <= 0:
            return effect_off(), {"mode": "off"}
        ratio = (second & 0x07) | ((first & 0x07) << 3)
        return _span_block(0x23, start, end, ratio, frequency), {
            "mode": mode, "start": start, "end": end,
            "firstFoot": first, "secondFoot": second, "frequency": frequency,
        }
    if mode == "machine":
        start = _clamp(params.get("start", 0), 0, 8)
        end = _clamp(params.get("end", 9), start + 1, 9)
        amplitude_a = _clamp(params.get("amplitudeA", 2), 0, 7)
        amplitude_b = _clamp(params.get("amplitudeB", 5), 0, 7)
        frequency = _clamp(params.get("frequency", 20), 0, 255)
        period = _clamp(params.get("period", 10), 0, 255)
        if frequency <= 0:
            return effect_off(), {"mode": "off"}
        pair = (amplitude_a & 0x07) | ((amplitude_b & 0x07) << 3)
        return _span_block(0x27, start, end, pair, frequency, period), {
            "mode": mode, "start": start, "end": end,
            "amplitudeA": amplitude_a, "amplitudeB": amplitude_b,
            "frequency": frequency, "period": period,
        }
    if mode == "vibration":
        position = _clamp(params.get("position", 0), 0, 9)
        amplitude = _clamp(params.get("amplitude", 0), 0, 8)
        frequency = _clamp(params.get("frequency", 30), 0, 255)
        zones = [0] * 10
        if amplitude > 0 and frequency > 0:
            for index in range(position, 10):
                zones[index] = amplitude
        block = _write_zones(0x26, zones, frequency if amplitude and frequency else 0)
        applied = {
            "mode": "vibration" if amplitude and frequency else "off",
            "position": position, "amplitude": amplitude, "frequency": frequency, "zones": zones,
        }
        return _as_off(block, applied)
    if mode == "vibration_zones":
        zones = [_clamp(v, 0, 8) for v in (params.get("zones") or [0] * 10)[:10]]
        zones += [0] * (10 - len(zones))
        frequency = _clamp(params.get("frequency", 30), 0, 255)
        if frequency <= 0 or not any(zones):
            return effect_off(), {"mode": "off"}
        return _write_zones(0x26, zones, frequency), {
            "mode": mode, "frequency": frequency, "zones": zones,
        }
    raise ValueError(mode)


def _as_off(block, applied):
    if block[0] == 0x05:
        return block, {"mode": "off"}
    return block, applied


def _span_block(mode_byte, start, end, third, fourth=0, fifth=0):
    zones = (1 << start) | (1 << end)
    block = bytearray(11)
    block[0] = mode_byte
    block[1] = zones & 0xFF
    block[2] = (zones >> 8) & 0xFF
    block[3] = third & 0xFF
    block[4] = fourth & 0xFF
    block[5] = fifth & 0xFF
    return block


def _touch(report, base):
    contact = report[base]
    x = report[base + 1] | ((report[base + 2] & 0x0F) << 8)
    y = (report[base + 2] >> 4) | (report[base + 3] << 4)
    return {
        "active": (contact & 0x80) == 0,
        "id": contact & 0x7F,
        "x": x,
        "y": y,
    }


def _calib_axis_gyro(bias, plus, minus, speed_2x):
    denom = abs(plus - bias) + abs(minus - bias)
    numer = speed_2x * 1024
    if denom == 0:
        return {"bias": bias, "plus": plus, "minus": minus, "numer": 2048 * 1024, "denom": 32767}
    return {"bias": bias, "plus": plus, "minus": minus, "numer": numer, "denom": denom}


def _calib_axis_acc(plus, minus):
    span = plus - minus
    bias = plus - span / 2
    if span == 0:
        return {"bias": 0, "plus": plus, "minus": minus, "numer": 4 * 8192, "denom": 32767}
    return {"bias": bias, "plus": plus, "minus": minus, "numer": 2 * 8192, "denom": span}


def decode_calibration(buf):
    vals = [_i16(buf, 1 + i * 2) for i in range(17)]
    speed = vals[9] + vals[10]
    gyro = {
        "x": _calib_axis_gyro(vals[0], vals[3], vals[4], speed),
        "y": _calib_axis_gyro(vals[1], vals[5], vals[6], speed),
        "z": _calib_axis_gyro(vals[2], vals[7], vals[8], speed),
    }
    accel = {
        "x": _calib_axis_acc(vals[11], vals[12]),
        "y": _calib_axis_acc(vals[13], vals[14]),
        "z": _calib_axis_acc(vals[15], vals[16]),
    }
    return {"gyro": gyro, "accel": accel, "raw": buf.hex()}


def _apply_calib(raw, axis, kind):
    if kind == "gyro":
        scaled = raw * axis["numer"] / axis["denom"]
        return scaled / 1024.0
    return (raw - axis["bias"]) * axis["numer"] / axis["denom"] / 8192.0


def decode_report(report, calibration):
    buttons = report[8:12]
    hat = buttons[0] & 0x0F
    down = [name for index, mask, name in BUTTONS if buttons[index] & mask]
    gyro_raw = [_i16(report, 16), _i16(report, 18), _i16(report, 20)]
    acc_raw = [_i16(report, 22), _i16(report, 24), _i16(report, 26)]
    names = ("x", "y", "z")
    gyro = {}
    accel = {}
    if calibration:
        for index, name in enumerate(names):
            gyro[name] = round(_apply_calib(gyro_raw[index], calibration["gyro"][name], "gyro"), 3)
            accel[name] = round(_apply_calib(acc_raw[index], calibration["accel"][name], "accel"), 4)
    status0 = report[53]
    level = status0 & 0x0F
    charge = status0 >> 4
    if charge == 0x2:
        percent = 100
    elif charge in (0x0, 0x1):
        percent = min(level * 10 + 5, 100)
    else:
        percent = 0
    status1 = report[54]
    return {
        "lx": report[1], "ly": report[2], "rx": report[3], "ry": report[4],
        "l2": report[5], "r2": report[6], "seq": report[7],
        "hat": hat if hat <= 8 else 8,
        "hatName": HAT[hat] if hat <= 8 else "center",
        "buttons": {name: name in down for _, _, name in BUTTONS},
        "gyroRaw": gyro_raw,
        "accelRaw": acc_raw,
        "gyro": gyro,
        "accel": accel,
        "stamp": _u32(report, 12),
        "sensorTs": _u32(report, 28),
        "touch": [_touch(report, 33), _touch(report, 37)],
        "battery": {
            "level": level,
            "percent": percent,
            "charge": CHARGE.get(charge, "unknown"),
            "chargeCode": charge,
            "raw": status0,
        },
        "jack": {
            "headphone": bool(status1 & 0x01),
            "mic": bool(status1 & 0x02),
            "muted": bool(status1 & 0x04),
            "raw": status1,
            "extra": report[55],
        },
        "triggerEcho": {"right": report[42], "left": report[43], "state": report[48]},
        "raw": report.hex(),
    }


def decode_identity(info_handle):
    identity = {
        "manufacturer": _hid_string(hid.HidD_GetManufacturerString, info_handle),
        "product": _hid_string(hid.HidD_GetProductString, info_handle),
        "vid": "054C",
        "pid": "0CE6",
        "bcdDevice": "0100",
    }
    fw = _feature(info_handle, 0x20, 64)
    if fw:
        identity["built"] = (
            fw[1:12].decode("ascii", "replace").strip()
            + " "
            + fw[12:20].decode("ascii", "replace").strip()
        )
        identity["hwVersion"] = f"0x{int.from_bytes(fw[24:28], 'little'):08X}"
        identity["fwVersion"] = f"0x{int.from_bytes(fw[28:32], 'little'):08X}"
        update = int.from_bytes(fw[44:46], "little")
        identity["updateVersion"] = f"{update >> 8}.{update & 0xFF}"
        identity["updateRaw"] = f"0x{update:04X}"
    pair = _feature(info_handle, 0x09, 20)
    if pair:
        mac = pair[1:7]
        identity["bluetooth"] = ":".join(f"{b:02X}" for b in reversed(mac))
    cal = _feature(info_handle, 0x05, 41)
    calibration = decode_calibration(cal) if cal else None
    return identity, calibration


@dataclass
class OutputState:
    rumble_left: int = 0
    rumble_right: int = 0
    left_effect: bytearray | None = None
    right_effect: bytearray | None = None
    light_cmd: str | None = None
    red: int = 0
    green: int = 0
    blue: int = 0
    brightness: int = 0
    player: int = 0
    mute_led: int = 0
    audio_set: bool = False
    speaker: int = 100
    headphone: int = 64
    mic: int = 32
    preamp: int = 2
    path: str = "speaker"
    mic_muted: bool = False


class DualSense:
    def __init__(self):
        self._lock = threading.Lock()
        self._reader = None
        self._writer = None
        self._event = None
        self._thread = None
        self._stop = threading.Event()
        self.path = None
        self.connected = False
        self.error = ""
        self.identity = {}
        self.calibration = None
        self.report = None
        self.decoded = {}
        self.hz = 0.0
        self.output = OutputState()
        self._drift = {"lx": 0, "ly": 0, "rx": 0, "ry": 0}
        self._ts_prev = None
        self._hz_window = []

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="dualsense-hid", daemon=True)
        self._thread.start()

    def stop(self):
        try:
            self.release_all()
        except OSError:
            pass
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.5)
        self._close_handles()

    def reconnect(self):
        self._close_handles()
        self.connected = False

    def snapshot(self):
        with self._lock:
            decoded = dict(self.decoded) if self.decoded else {}
            if decoded:
                decoded = {
                    **decoded,
                    "drift": dict(self._drift),
                }
            return {
                "connected": self.connected,
                "error": self.error,
                "path": self.path or "",
                "hz": round(self.hz, 1),
                "identity": dict(self.identity),
                "calibration": self.calibration,
                "input": decoded,
                "command": {
                    "rumbleLeft": self.output.rumble_left,
                    "rumbleRight": self.output.rumble_right,
                    "light": self.output.light_cmd,
                    "color": [self.output.red, self.output.green, self.output.blue],
                    "brightness": self.output.brightness,
                    "player": self.output.player,
                    "muteLed": self.output.mute_led,
                    "audio": self.output.audio_set,
                    "speaker": self.output.speaker,
                    "headphone": self.output.headphone,
                    "mic": self.output.mic,
                    "preamp": self.output.preamp,
                    "path": self.output.path,
                    "micMuted": self.output.mic_muted,
                    "leftEffect": bytes(self.output.left_effect).hex() if self.output.left_effect else "",
                    "rightEffect": bytes(self.output.right_effect).hex() if self.output.right_effect else "",
                },
            }

    def reset_drift(self):
        with self._lock:
            self._drift = {"lx": 0, "ly": 0, "rx": 0, "ry": 0}

    def set_rumble(self, left, right):
        with self._lock:
            self.output.rumble_left = _clamp(left, 0, 255)
            self.output.rumble_right = _clamp(right, 0, 255)
            self._send_locked()

    def set_trigger(self, side, mode, params):
        block, applied = encode_effect(mode, params)
        with self._lock:
            if side in ("left", "both"):
                self.output.left_effect = bytearray(block)
            if side in ("right", "both"):
                self.output.right_effect = bytearray(block)
            self._send_locked()
        return {"ok": True, "applied": applied, "effect": bytes(block).hex()}

    def set_triggers(self, left, right):
        left = left or {}
        right = right or {}
        left_block, left_applied = encode_effect(left.get("mode", "off"), left.get("params") or {})
        right_block, right_applied = encode_effect(right.get("mode", "off"), right.get("params") or {})
        with self._lock:
            self.output.left_effect = bytearray(left_block)
            self.output.right_effect = bytearray(right_block)
            self._send_locked()
        return {
            "ok": True,
            "left": {"applied": left_applied, "effect": bytes(left_block).hex()},
            "right": {"applied": right_applied, "effect": bytes(right_block).hex()},
        }

    def set_light(self, red, green, blue, brightness, player, mute_led, command):
        with self._lock:
            self.output.red = _clamp(red, 0, 255)
            self.output.green = _clamp(green, 0, 255)
            self.output.blue = _clamp(blue, 0, 255)
            self.output.brightness = _clamp(brightness, 0, 255)
            self.output.player = _clamp(player, 0, 31)
            self.output.mute_led = _clamp(mute_led, 0, 2)
            self.output.light_cmd = command
            self._send_locked()

    def set_audio(self, speaker, headphone, mic, preamp, path, mic_muted):
        with self._lock:
            self.output.audio_set = True
            self.output.speaker = _clamp(speaker, 0, 255)
            self.output.headphone = _clamp(headphone, 0, 127)
            self.output.mic = _clamp(mic, 0, 64)
            self.output.preamp = _clamp(preamp, 0, 7)
            self.output.path = "headphone" if path == "headphone" else "speaker"
            self.output.mic_muted = bool(mic_muted)
            self._send_locked()

    def release_all(self):
        with self._lock:
            off = effect_off()
            self.output.rumble_left = 0
            self.output.rumble_right = 0
            self.output.left_effect = bytearray(off)
            self.output.right_effect = bytearray(off)
            self.output.light_cmd = "release"
            self.output.mute_led = 0
            self.output.mic_muted = False
            if self._writer:
                try:
                    self._send_locked()
                except OSError as exc:
                    self.error = str(exc)

    def _send_locked(self):
        if not self._writer:
            raise OSError("not connected")
        packet = bytes([0x02]) + bytes(self._build_locked())
        buf = ctypes.create_string_buffer(packet)
        wrote = wintypes.DWORD(0)
        if not kernel32.WriteFile(self._writer, buf, len(packet), ctypes.byref(wrote), None):
            err = ctypes.get_last_error()
            self.error = f"write {err}"
            raise OSError(err)

    def _build_locked(self):
        out = self.output
        report = bytearray(47)
        report[0] |= 0x02
        report[38] |= 0x04
        report[2] = out.rumble_right
        report[3] = out.rumble_left
        if out.right_effect is not None:
            report[0] |= 0x04
            report[10:21] = out.right_effect
        if out.left_effect is not None:
            report[0] |= 0x08
            report[21:32] = out.left_effect
        if out.light_cmd == "color":
            report[1] |= 0x04 | 0x10 | 0x01
            report[38] |= 0x02
            report[8] = out.mute_led
            report[42] = out.brightness
            report[43] = out.player
            report[44] = out.red
            report[45] = out.green
            report[46] = out.blue
        elif out.light_cmd == "off":
            report[1] |= 0x01
            report[8] = out.mute_led
            report[38] |= 0x02
            report[41] = 0x02
        elif out.light_cmd == "release":
            report[1] |= 0x08
        if out.audio_set:
            report[0] |= 0x80 | 0x40
            report[6] = out.mic
            report[1] |= 0x02
            if out.mic_muted:
                report[9] |= 0x10
            if out.path == "headphone":
                report[0] |= 0x10
                report[4] = out.headphone
                report[7] = 0x00
            else:
                report[0] |= 0x20
                report[5] = out.speaker
                report[7] = 0x30
                report[1] |= 0x80
                report[37] = out.preamp & 0x07
        return report

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._open_devices()
                self._read_forever()
            except Exception as exc:  # noqa: BLE001 - keep the device thread alive
                with self._lock:
                    self.connected = False
                    self.error = str(exc)
                self._close_handles()
                self._stop.wait(0.8)

    def _open_devices(self):
        path = find_dualsense_path()
        if not path:
            raise OSError("DualSense not found")
        info = _open(path, GENERIC_READ | GENERIC_WRITE, 0)
        try:
            identity, calibration = decode_identity(info)
        finally:
            kernel32.CloseHandle(info)
        reader = _open(path, GENERIC_READ, FILE_FLAG_OVERLAPPED)
        writer = _open(path, GENERIC_WRITE, 0)
        event = kernel32.CreateEventW(None, True, False, None)
        with self._lock:
            self.path = path
            self.identity = identity
            self.calibration = calibration
            self._reader = reader
            self._writer = writer
            self._event = event
            self.connected = True
            self.error = ""
            self._ts_prev = None
            self._hz_window.clear()

    def _close_handles(self):
        with self._lock:
            reader, writer, event = self._reader, self._writer, self._event
            self._reader = None
            self._writer = None
            self._event = None
            self.connected = False
        if reader:
            kernel32.CancelIoEx(reader, None)
            kernel32.CloseHandle(reader)
        if writer:
            kernel32.CloseHandle(writer)
        if event:
            kernel32.CloseHandle(event)

    def _read_one(self):
        buf = ctypes.create_string_buffer(64)
        nread = wintypes.DWORD(0)
        ov = OVERLAPPED()
        ov.hEvent = self._event
        kernel32.ResetEvent(self._event)
        ok = kernel32.ReadFile(self._reader, buf, 64, ctypes.byref(nread), ctypes.byref(ov))
        if not ok:
            if ctypes.get_last_error() != ERROR_IO_PENDING:
                raise OSError(ctypes.get_last_error())
            if kernel32.WaitForSingleObject(self._event, 800) != 0:
                kernel32.CancelIoEx(self._reader, ctypes.byref(ov))
                raise TimeoutError("input report")
            if not kernel32.GetOverlappedResult(self._reader, ctypes.byref(ov), ctypes.byref(nread), False):
                raise OSError(ctypes.get_last_error())
        data = bytes(buf[:nread.value])
        if len(data) < 64 or data[0] != 0x01:
            return None
        return data

    def _read_forever(self):
        while not self._stop.is_set():
            data = self._read_one()
            if data is None:
                continue
            with self._lock:
                self.report = data
                self.decoded = decode_report(data, self.calibration)
                for key in self._drift:
                    self._drift[key] = max(self._drift[key], abs(self.decoded[key] - 128))
                ts = self.decoded["sensorTs"]
                if self._ts_prev is not None:
                    delta = (ts - self._ts_prev) & 0xFFFFFFFF
                    if delta:
                        self._hz_window.append(1_000_000 / (delta / 3))
                        if len(self._hz_window) > 40:
                            self._hz_window.pop(0)
                        self.hz = sum(self._hz_window) / len(self._hz_window)
                self._ts_prev = ts
