const $ = (id) => document.getElementById(id);
const BUTTONS = ["square", "cross", "circle", "triangle", "l1", "r1", "l2", "r2", "create", "options", "l3", "r3", "ps", "touchpad", "mute"];
const HAT_CELLS = ["nw", "n", "ne", "w", "center", "e", "sw", "s", "se"];
const PLAYER = [0x04, 0x0a, 0x15, 0x1b, 0x1f];
let T = {};
let lang = "en";
let toastTimer = 0;

function n(id) { return Number($(id).value); }
function t(key) { return T[key] || key; }

function toast(message) {
  const el = $("toast");
  el.hidden = !message;
  el.textContent = message || "";
  clearTimeout(toastTimer);
  if (message) toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
}

function applyText() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "fa" ? "rtl" : "ltr";
  document.title = t("appTitle");
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (!T[key]) return;
    if (el.tagName === "OPTGROUP") {
      el.label = T[key];
      return;
    }
    const slot = el.querySelector("[data-slot]");
    if (slot) slot.textContent = T[key];
    else el.textContent = T[key];
  });
  document.querySelectorAll("select").forEach((el) => {
    const index = el.selectedIndex;
    el.selectedIndex = -1;
    el.selectedIndex = index < 0 ? 0 : index;
  });
  paintSelects();
  $("lang").textContent = t("language");
}

async function setLang(next) {
  lang = next === "fa" ? "fa" : "en";
  T = await window.pywebview.api.get_strings(lang);
  await window.pywebview.api.set_language(lang);
  applyText();
  buildStatic();
}

function buildStatic() {
  const dpad = $("dpad");
  dpad.innerHTML = HAT_CELLS.map((name) => `<b data-hat="${name}">${t(name)}</b>`).join("");
  $("keys").innerHTML = BUTTONS.map((name) => {
    const label = name === "touchpad" ? t("touchpadClick") : t(name);
    return `<b data-key="${name}">${label}</b>`;
  }).join("");
  mountEditors(snapshotEditors());
  $("leds").innerHTML = [0, 1, 2, 3, 4].map((bit) =>
    `<label class="check"><input type="checkbox" data-led="${bit}" ${bit === 2 ? "checked" : ""} /><span>${bit + 1}</span></label>`
  ).join("");
  $("player-presets").innerHTML = PLAYER.map((mask, index) =>
    `<button type="button" data-player="${mask}">${index + 1}</button>`
  ).join("");
  $("player-presets").querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => setPlayer(Number(btn.dataset.player)));
  });
  syncAlarmKind();
  mirrorRanges();
}

function setPlayer(mask) {
  document.querySelectorAll("[data-led]").forEach((box) => {
    box.checked = (mask & (1 << Number(box.dataset.led))) !== 0;
  });
}

function playerMask() {
  let mask = 0;
  document.querySelectorAll("[data-led]").forEach((box) => {
    if (box.checked) mask |= 1 << Number(box.dataset.led);
  });
  return mask;
}

const editorZones = new WeakMap();
const DEFAULT_ZONES = [2, 2, 2, 2, 2, 6, 6, 6, 6, 6];
const PRESETS = {
  loose: ["feedback", { position: 0, strength: 1 }],
  firm: ["feedback", { position: 0, strength: 8 }],
  click: ["weapon", { wstart: 2, wend: 5, wstrength: 6 }],
  full: ["feedback", { position: 8, strength: 8 }],
  half: ["feedback", { position: 5, strength: 8 }],
  rifle: ["vibration", { vpos: 0, vamp: 8, vfreq: 10 }],
};
const MODE_NOTES = {
  off: "triggerHelp",
  feedback: "triggerHelp",
  slope: "triggerHelp",
  zones: "triggerHelp",
  weapon: "weaponHelp",
  vibration: "triggerHelp",
  vibration_zones: "triggerHelp",
  bow: "bowHelp",
  galloping: "gallopingHelp",
  machine: "machineHelp",
};

function field(editor, name) {
  return editor.querySelector(`[data-field="${name}"]`);
}

function fieldNum(editor, name) {
  return Number(field(editor, name).value);
}

function snapshotEditors() {
  const snaps = {};
  document.querySelectorAll("#trigger-editors .trigger-editor").forEach((editor) => {
    const fields = {};
    editor.querySelectorAll("[data-field]").forEach((el) => { fields[el.dataset.field] = el.value; });
    snaps[editor.dataset.side] = { fields, zones: (editorZones.get(editor) || DEFAULT_ZONES).slice() };
  });
  return snaps;
}

function mountEditors(snaps) {
  const host = $("trigger-editors");
  if (!host) return;
  const split = $("tr-split").checked;
  const sides = split ? ["left", "right"] : ["shared"];
  host.replaceChildren();
  sides.forEach((side) => {
    const editor = $("trigger-editor").content.firstElementChild.cloneNode(true);
    editor.dataset.side = side;
    const title = editor.querySelector(".editor-title");
    const sideField = editor.querySelector(".side-field");
    if (split) {
      title.hidden = false;
      title.textContent = side === "left" ? t("l2") : t("r2");
      sideField.hidden = true;
    }
    const snap = snaps[side] || (side === "right" ? snaps.left : null) || snaps.shared || null;
    const zones = snap && snap.zones ? snap.zones.slice() : DEFAULT_ZONES.slice();
    editorZones.set(editor, zones);
    if (snap) {
      editor.querySelectorAll("[data-field]").forEach((el) => {
        if (snap.fields[el.dataset.field] != null) el.value = snap.fields[el.dataset.field];
      });
    }
    host.appendChild(editor);
    paintBars(editor.querySelector(".zone-box"), zones);
  });
  $("tr-both-actions").hidden = !split;
  $("split-note").hidden = !split;
  applyText();
  document.querySelectorAll("#trigger-editors .trigger-editor").forEach(syncEditor);
  mirrorRanges();
}

function syncEditor(editor) {
  const mode = field(editor, "mode").value;
  editor.querySelectorAll("[data-modes]").forEach((el) => {
    el.hidden = !el.dataset.modes.split(" ").includes(mode);
  });
  tieRange(editor, "sstart", "send", 9);
  tieRange(editor, "wstart", "wend", 8);
  tieRange(editor, "bstart", "bend", 8);
  tieRange(editor, "gstart", "gend", 9);
  tieRange(editor, "mstart", "mend", 9);
  tieRange(editor, "foot1", "foot2", 7);
  editor.querySelector(".mode-note").textContent = t(MODE_NOTES[mode] || "triggerHelp");
  editor.querySelector(".firmware-note").hidden = !["bow", "galloping", "machine"].includes(mode);
  paintZonePreview(editor);
}

function tieRange(editor, startName, endName, endMax) {
  const start = field(editor, startName);
  const end = field(editor, endName);
  if (!start || !end) return;
  const floor = Number(start.value) + 1;
  end.min = String(floor);
  end.max = String(endMax);
  if (Number(end.value) < floor) end.value = String(floor);
  if (Number(end.value) > endMax) end.value = String(endMax);
}

function paintBars(host, values) {
  if (!host) return;
  const cells = host.querySelectorAll(".zcell");
  if (cells.length !== values.length) {
    host.innerHTML = values.map((value, index) => {
      const height = value <= 0 ? 0 : (value / 8) * 100;
      return `<div class="zcell" data-zone="${index}"><i style="height:${height}%"></i><b>${index}</b></div>`;
    }).join("");
    return;
  }
  cells.forEach((cell, index) => {
    const value = values[index] || 0;
    cell.querySelector("i").style.height = value <= 0 ? "0" : `${(value / 8) * 100}%`;
  });
}

function effectShape(editor) {
  const mode = field(editor, "mode").value;
  const zones = Array(10).fill(0);
  const fill = (start, end, level) => {
    for (let index = start; index <= end && index < 10; index += 1) zones[index] = level;
  };
  if (mode === "feedback") {
    fill(fieldNum(editor, "position"), 9, fieldNum(editor, "strength"));
  } else if (mode === "slope") {
    const start = fieldNum(editor, "sstart");
    const end = Math.max(start + 1, fieldNum(editor, "send"));
    const span = end - start;
    for (let index = start; index < 10; index += 1) {
      const raw = index <= end
        ? fieldNum(editor, "ss") + (fieldNum(editor, "es") - fieldNum(editor, "ss")) * (index - start) / span
        : fieldNum(editor, "es");
      zones[index] = Math.max(1, Math.min(8, Math.round(raw)));
    }
  } else if (mode === "zones" || mode === "vibration_zones") {
    return (editorZones.get(editor) || DEFAULT_ZONES).slice();
  } else if (mode === "weapon") {
    fill(fieldNum(editor, "wstart"), fieldNum(editor, "wend"), fieldNum(editor, "wstrength"));
  } else if (mode === "vibration") {
    fill(fieldNum(editor, "vpos"), 9, fieldNum(editor, "vamp"));
  } else if (mode === "bow") {
    fill(fieldNum(editor, "bstart"), fieldNum(editor, "bend"), fieldNum(editor, "bstrength"));
  } else if (mode === "galloping") {
    fill(fieldNum(editor, "gstart"), fieldNum(editor, "gend"), 6);
  } else if (mode === "machine") {
    fill(fieldNum(editor, "mstart"), fieldNum(editor, "mend"), Math.max(fieldNum(editor, "ampa"), fieldNum(editor, "ampb")));
  }
  return zones;
}

function paintZonePreview(editor) {
  const zones = editorZones.get(editor) || DEFAULT_ZONES;
  paintBars(editor.querySelector(".zone-box"), zones);
  const host = editor.querySelector(".zone-preview");
  if (!host || host.hidden) return;
  paintBars(host, effectShape(editor));
}

function editZoneAt(editor, event) {
  const host = editor.querySelector(".zone-box");
  if (!host || host.hidden) return;
  const rect = host.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const zones = editorZones.get(editor);
  const index = Math.max(0, Math.min(9, Math.floor(((event.clientX - rect.left) / rect.width) * 10)));
  const ratio = 1 - (event.clientY - rect.top) / rect.height;
  zones[index] = Math.max(0, Math.min(8, Math.round(ratio * 8)));
  paintBars(host, zones);
}

function triggerParams(editor) {
  const mode = field(editor, "mode").value;
  const zones = (editorZones.get(editor) || DEFAULT_ZONES).slice();
  if (mode === "feedback") return { position: fieldNum(editor, "position"), strength: fieldNum(editor, "strength") };
  if (mode === "slope") return { start: fieldNum(editor, "sstart"), end: fieldNum(editor, "send"), startStrength: fieldNum(editor, "ss"), endStrength: fieldNum(editor, "es") };
  if (mode === "zones") return { zones };
  if (mode === "weapon") return { start: fieldNum(editor, "wstart"), end: fieldNum(editor, "wend"), strength: fieldNum(editor, "wstrength") };
  if (mode === "vibration") return { position: fieldNum(editor, "vpos"), amplitude: fieldNum(editor, "vamp"), frequency: fieldNum(editor, "vfreq") };
  if (mode === "vibration_zones") return { frequency: fieldNum(editor, "zfreq"), zones };
  if (mode === "bow") return { start: fieldNum(editor, "bstart"), end: fieldNum(editor, "bend"), strength: fieldNum(editor, "bstrength"), snapForce: fieldNum(editor, "snap") };
  if (mode === "galloping") return { start: fieldNum(editor, "gstart"), end: fieldNum(editor, "gend"), firstFoot: fieldNum(editor, "foot1"), secondFoot: fieldNum(editor, "foot2"), frequency: fieldNum(editor, "gfreq") };
  if (mode === "machine") return { start: fieldNum(editor, "mstart"), end: fieldNum(editor, "mend"), amplitudeA: fieldNum(editor, "ampa"), amplitudeB: fieldNum(editor, "ampb"), frequency: fieldNum(editor, "mfreq"), period: fieldNum(editor, "period") };
  return {};
}

function editorPayload(editor, mode) {
  const chosen = mode || field(editor, "mode").value;
  const side = editor.dataset.side === "shared" ? field(editor, "side").value : editor.dataset.side;
  return { side, mode: chosen, params: chosen === "off" ? {} : triggerParams(editor) };
}

function formatEffect(hex) {
  const bytes = (hex || "").match(/.{2}/g) || [];
  if (!bytes.length) return "";
  return `${t("modeByte")} 0x${bytes[0]} · ${bytes.join(" ")}`;
}

function syncAlarmKind() {
  const kind = $("al-kind").value;
  document.querySelectorAll("[data-alarm]").forEach((el) => {
    el.hidden = el.dataset.alarm !== kind;
  });
}

function colorParts() {
  const hex = $("color").value;
  return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
}

function setColorInputs(r, g, b) {
  const hex = `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
  $("color").value = hex;
  $("c-r").value = r;
  $("c-g").value = g;
  $("c-b").value = b;
  document.documentElement.style.setProperty("--accent", hex);
}

async function applyEditor(editor, mode) {
  const payload = editorPayload(editor, mode);
  const result = await window.pywebview.api.set_trigger(payload.side, payload.mode, payload.params);
  if (!result.ok) toast(result.error);
  else editor.querySelector(".tr-result").textContent = formatEffect(result.effect);
}

async function applyBoth(mode) {
  const editors = [...document.querySelectorAll("#trigger-editors .trigger-editor")];
  const left = editorPayload(editors.find((editor) => editor.dataset.side === "left"), mode);
  const right = editorPayload(editors.find((editor) => editor.dataset.side === "right"), mode);
  const result = await window.pywebview.api.set_triggers(
    { mode: left.mode, params: left.params },
    { mode: right.mode, params: right.params },
  );
  if (!result.ok) {
    toast(result.error);
    return;
  }
  editors[0].querySelector(".tr-result").textContent = formatEffect(result.left.effect);
  editors[1].querySelector(".tr-result").textContent = formatEffect(result.right.effect);
}

function paintBar(id, value, max) {
  const el = $(id);
  if (el) el.style.width = `${Math.max(0, Math.min(100, (value / max) * 100))}%`;
}

function axisBlock(target, values, unit, max) {
  const host = $(target);
  if (!host || !values) return;
  host.innerHTML = ["x", "y", "z"].map((name, index) => {
    const value = values[name] ?? values[index] ?? 0;
    const width = Math.min(100, Math.abs(value) / max * 100);
    return `<div class="barline"><span>${name.toUpperCase()}</span><i style="width:${width}%"></i><span>${value} ${unit}</span></div>`;
  }).join("");
}

function dl(id, rows) {
  const host = $(id);
  if (!host) return;
  host.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
}

function render(state) {
  const input = state.input || {};
  $("conn").innerHTML = state.connected ? `<b>${t("connected")}</b>` : t("disconnected");
  $("hz").textContent = state.connected ? `${state.hz} ${t("hz")}` : "";
  const battery = input.battery || {};
  $("bat").textContent = state.connected ? `${battery.percent ?? "–"}% · ${t(battery.charge || "unknown")}` : "";
  const audio = state.audio || {};
  $("audio-name").textContent = audio.available
    ? `${audio.outputName || ""} / ${audio.inputName || ""}`
    : (audio.error || t("audioMissing"));
  paintBar("mic-bar", Math.round((audio.level || 0) * 100), 100);
  const alarm = state.alarm || {};
  $("alarm-state").textContent = alarm.firing
    ? t("firing")
    : (alarm.armed ? `${t("armed")} ${alarm.remaining}s` : t("idleAlarm"));
  dl("dev-dl", [
    [t("connected"), state.connected ? t("connected") : t("disconnected")],
    [t("rate"), `${state.hz} ${t("hz")}`],
    ["HID", state.path || ""],
  ]);
  $("dev-err").textContent = [state.error, audio.error].filter(Boolean).join("\n");
  if (input.lx === undefined) return;

  const place = (id, x, y) => {
    const dot = $(id);
    dot.style.left = `${(x / 255) * 100}%`;
    dot.style.top = `${(y / 255) * 100}%`;
  };
  place("dot-l", input.lx, input.ly);
  place("dot-r", input.rx, input.ry);
  $("lx").textContent = `X ${input.lx}`;
  $("ly").textContent = `Y ${input.ly}`;
  $("rx").textContent = `X ${input.rx}`;
  $("ry").textContent = `Y ${input.ry}`;
  const drift = input.drift || {};
  $("drift-l").textContent = `${drift.lx} / ${drift.ly}`;
  $("drift-r").textContent = `${drift.rx} / ${drift.ry}`;
  paintBar("bar-l2", input.l2, 255);
  paintBar("bar-r2", input.r2, 255);
  paintBar("bar-l2b", input.l2, 255);
  paintBar("bar-r2b", input.r2, 255);
  $("l2v").textContent = input.l2;
  $("r2v").textContent = input.r2;
  document.querySelectorAll("[data-hat]").forEach((cell) => {
    cell.classList.toggle("on", cell.dataset.hat === input.hatName);
  });
  $("hat-label").textContent = `${input.hat} ${t(input.hatName || "center")}`;
  document.querySelectorAll("[data-key]").forEach((cell) => {
    cell.classList.toggle("on", !!(input.buttons && input.buttons[cell.dataset.key]));
  });
  const touch = input.touch || [{}, {}];
  touch.forEach((point, index) => {
    const dot = $(`t${index}`);
    dot.style.left = `${(point.x / 1920) * 100}%`;
    dot.style.top = `${(point.y / 1080) * 100}%`;
    dot.style.opacity = point.active ? "1" : "0.25";
  });
  $("touch-read").textContent = touch.map((point, index) =>
    `${t("point")} ${index + 1} ${point.active ? t("active") : t("idle")} #${point.id} ${point.x},${point.y}`
  ).join("   ");
  axisBlock("gyro-bars", input.gyro, t("deg"), 200);
  axisBlock("acc-bars", input.accel, "g", 2);
  axisBlock("acc-live", input.accel, "g", 2);
  $("bat-pct").textContent = `${battery.percent ?? 0}%`;
  dl("bat-dl", [
    [t("level"), battery.level],
    [t("percent"), battery.percent],
    [t("battery"), t(battery.charge || "unknown")],
    [t("statusByte"), `0x${(battery.raw ?? 0).toString(16).padStart(2, "0")}`],
  ]);
  const jack = input.jack || {};
  const jackRows = [
    [t("headphone"), jack.headphone ? t("plugged") : t("empty")],
    [t("microphone"), jack.mic ? t("plugged") : t("empty")],
    [t("hwMute"), jack.muted ? t("on") : t("off")],
    [t("statusByte"), `0x${(jack.raw ?? 0).toString(16).padStart(2, "0")} / 0x${(jack.extra ?? 0).toString(16).padStart(2, "0")}`],
  ];
  dl("jack-dl", jackRows);
  dl("jack-audio", jackRows);
  const echo = input.triggerEcho || {};
  const echoRows = [
    [t("right"), `0x${(echo.right ?? 0).toString(16).padStart(2, "0")}`],
    [t("left"), `0x${(echo.left ?? 0).toString(16).padStart(2, "0")}`],
    [t("statusByte"), `0x${(echo.state ?? 0).toString(16).padStart(2, "0")}`],
  ];
  dl("echo-dl", echoRows);
  dl("echo-side", echoRows);
  const id = state.identity || {};
  dl("id-dl", [
    [t("product"), id.product || ""],
    ["USB", `${id.vid || "054C"}:${id.pid || "0CE6"}`],
    [t("built"), id.built || ""],
    [t("hw"), id.hwVersion || ""],
    [t("fw"), id.fwVersion || ""],
    [t("feature"), id.updateVersion || ""],
    [t("bt"), id.bluetooth || ""],
  ]);
  $("seq").textContent = input.seq;
  $("sts").textContent = input.sensorTs;
  const cal = state.calibration;
  if (cal) {
    const lines = ["gyro", "accel"].flatMap((kind) =>
      ["x", "y", "z"].map((axis) => {
        const item = cal[kind][axis];
        return `${kind} ${axis}: ${t("bias")} ${Math.round(item.bias)}  ${t("plus")} ${item.plus}  ${t("minus")} ${item.minus}`;
      })
    );
    $("cal").textContent = lines.join("\n");
  }
  $("raw").textContent = (input.raw || "").replace(/(.{2})/g, "$1 ").trim();
}

function paintSelects() {
  document.querySelectorAll("select").forEach((el) => {
    let face = el.parentElement.querySelector(":scope > .sel");
    if (!face) {
      face = document.createElement("span");
      face.className = "sel";
      el.after(face);
      el.addEventListener("change", () => {
        face.textContent = el.selectedOptions[0] ? el.selectedOptions[0].textContent : "";
      });
    }
    face.textContent = el.selectedOptions[0] ? el.selectedOptions[0].textContent : "";
  });
}

function mirrorRanges() {
  document.querySelectorAll('input[type="range"]').forEach((el) => {
    let out = el.parentElement.querySelector(":scope > .val");
    if (!out) {
      out = document.createElement("b");
      out.className = "val";
      el.after(out);
    }
    const paint = () => {
      out.textContent = el.value;
      const min = Number(el.min || 0);
      const max = Number(el.max || 100) || 1;
      const pct = Math.max(0, Math.min(100, ((Number(el.value) - min) / (max - min)) * 100));
      const dir = el.classList.contains("zone")
        ? "top"
        : (document.documentElement.dir === "rtl" ? "left" : "right");
      el.style.background = `linear-gradient(to ${dir}, var(--accent) ${pct}%, rgba(120,120,128,0.32) ${pct}%)`;
    };
    paint();
    if (!el.dataset.valued) {
      el.dataset.valued = "1";
      el.addEventListener("input", paint);
    }
  });
}

function bind() {
  document.querySelectorAll("nav button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("nav button").forEach((item) => item.classList.remove("on"));
      btn.classList.add("on");
      btn.scrollIntoView({ inline: "nearest", block: "nearest" });
      document.querySelectorAll("main section").forEach((section) => {
        const show = section.id === `page-${btn.dataset.page}`;
        section.hidden = !show;
        if (show) {
          section.classList.remove("enter");
          void section.offsetWidth;
          section.classList.add("enter");
        }
      });
    });
  });
  $("lang").addEventListener("click", () => setLang(lang === "en" ? "fa" : "en"));
  $("stop-all").addEventListener("click", () => window.pywebview.api.release_all());
  $("dev-free").addEventListener("click", () => window.pywebview.api.release_all());
  $("reset-drift").addEventListener("click", () => window.pywebview.api.reset_drift());
  $("trigger-shell").addEventListener("submit", (event) => event.preventDefault());
  $("tr-split").addEventListener("change", () => {
    const snaps = snapshotEditors();
    if ($("tr-split").checked) {
      const base = snaps.shared || snaps.left;
      mountEditors({ left: base, right: base ? JSON.parse(JSON.stringify(base)) : null });
    } else {
      mountEditors({ shared: snaps.left || snaps.shared });
    }
  });
  $("trigger-editors").addEventListener("input", (event) => {
    const editor = event.target.closest(".trigger-editor");
    if (editor) syncEditor(editor);
  });
  $("trigger-editors").addEventListener("change", (event) => {
    const editor = event.target.closest(".trigger-editor");
    if (editor) syncEditor(editor);
  });
  $("trigger-editors").addEventListener("pointerdown", (event) => {
    const editor = event.target.closest(".trigger-editor");
    const box = event.target.closest(".zone-box");
    if (!editor || !box || box.hidden) return;
    editZoneAt(editor, event);
    const move = (ev) => editZoneAt(editor, ev);
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
  $("trigger-editors").addEventListener("click", (event) => {
    const editor = event.target.closest(".trigger-editor");
    if (!editor) return;
    const preset = event.target.closest("[data-preset]");
    if (preset) {
      const [mode, values] = PRESETS[preset.dataset.preset];
      field(editor, "mode").value = mode;
      Object.entries(values).forEach(([name, value]) => { field(editor, name).value = value; });
      syncEditor(editor);
      applyEditor(editor);
      return;
    }
    if (event.target.closest(".tr-apply")) applyEditor(editor);
    if (event.target.closest(".tr-off")) applyEditor(editor, "off");
  });
  $("tr-apply-both").addEventListener("click", () => applyBoth());
  $("tr-off-both").addEventListener("click", () => applyBoth("off"));
  $("rum-hold").addEventListener("click", async () => {
    const result = await window.pywebview.api.set_rumble(n("rum-l"), n("rum-r"));
    if (!result.ok) toast(result.error);
  });
  $("rum-pulse").addEventListener("click", async () => {
    const result = await window.pywebview.api.pulse_rumble(n("rum-l"), n("rum-r"), n("rum-ms"));
    if (!result.ok) toast(result.error);
  });
  $("rum-stop").addEventListener("click", async () => {
    $("rum-l").value = 0; $("rum-r").value = 0;
    await window.pywebview.api.stop_rumble();
  });
  const syncColor = () => setColorInputs(n("c-r"), n("c-g"), n("c-b"));
  ["c-r", "c-g", "c-b"].forEach((id) => $(id).addEventListener("input", syncColor));
  $("color").addEventListener("input", () => {
    const [r, g, b] = colorParts();
    $("c-r").value = r; $("c-g").value = g; $("c-b").value = b;
    document.documentElement.style.setProperty("--accent", $("color").value);
  });
  $("light-send").addEventListener("click", async () => {
    const result = await window.pywebview.api.set_light(n("c-r"), n("c-g"), n("c-b"), n("c-br"), playerMask(), n("mute-led"), "color");
    if (!result.ok) toast(result.error);
  });
  $("light-off").addEventListener("click", () => window.pywebview.api.set_light(0, 0, 0, 0, playerMask(), n("mute-led"), "off"));
  $("light-release").addEventListener("click", () => window.pywebview.api.set_light(0, 0, 0, 0, 0, 0, "release"));
  $("audio-send").addEventListener("click", async () => {
    const result = await window.pywebview.api.set_audio(n("vol-sp"), n("vol-hp"), n("vol-mic"), n("vol-pre"), $("vol-path").value, $("mic-mute").checked);
    if (!result.ok) toast(result.error);
  });
  $("tone-play").addEventListener("click", async () => {
    const result = await window.pywebview.api.play_tone(n("tone-f"), n("tone-ms"));
    if (!result.ok) toast(result.error);
  });
  $("al-kind").addEventListener("change", syncAlarmKind);
  $("al-arm").addEventListener("click", async () => {
    const hex = $("al-color").value;
    const color = [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
    const mode = $("al-tmode").value;
    const strength = n("al-str");
    const trigger = mode === "weapon"
      ? { start: 2, end: 5, strength }
      : (mode === "vibration" ? { position: 0, amplitude: strength, frequency: 40 } : { position: 0, strength });
    const result = await window.pywebview.api.arm_alarm({
      kind: $("al-kind").value,
      seconds: n("al-sec"),
      hour: n("al-h"),
      minute: n("al-m"),
      snooze: n("al-sn"),
      tone: n("al-tone"),
      color,
      player: 0x04,
      triggerMode: mode,
      trigger,
      channels: {
        speaker: $("ch-sp").checked,
        rumbleL: $("ch-rl").checked,
        rumbleR: $("ch-rr").checked,
        light: $("ch-li").checked,
        player: $("ch-pl").checked,
        left: $("ch-tl").checked,
        right: $("ch-tr").checked,
      },
    });
    if (!result.ok) toast(result.error);
  });
  $("al-snooze").addEventListener("click", () => window.pywebview.api.snooze_alarm());
  $("al-stop").addEventListener("click", () => window.pywebview.api.stop_alarm());
  $("dev-re").addEventListener("click", () => window.pywebview.api.reconnect());
}

async function tick() {
  try {
    render(await window.pywebview.api.get_state());
  } catch (err) {
    $("conn").textContent = String(err);
  }
}

function pinNav() {
  const current = document.querySelector("nav button.on");
  if (current) current.scrollIntoView({ inline: "center", block: "nearest" });
}
window.addEventListener("resize", pinNav);
window.addEventListener("pywebviewready", async () => {
  const settings = await window.pywebview.api.get_settings();
  lang = settings.lang === "fa" ? "fa" : "en";
  T = await window.pywebview.api.get_strings(lang);
  applyText();
  buildStatic();
  bind();
  pinNav();
  setInterval(tick, 50);
});
