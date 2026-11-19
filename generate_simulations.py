"""
Generate Edited 3D Push Fatigue Simulation Videos for All Load Cells & Subjects
===============================================================================
Takes the base 3D simulation video (`push_fatigue_3d_video.mp4`), tracks the
hanging dead-weight badge, replaces the telemetry HUD and dead-weight label per
(load, subject), and embeds a live animated RMS & MDF simulation graph panel
driven by the exact 36-window EMG metrics in `web/data/mtp_data.json`.

Outputs H.264 MP4s (browser-ready) to:
  - web/simulations/<load_id>/<subject_id>.mp4
  - public/simulations/<load_id>/<subject_id>.mp4  (mirrored for deployment)
  - docs/simulations/<load_id>/<subject_id>.mp4    (mirrored for static docs)
"""

import os
import sys
import json
import time
import shutil
import subprocess
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
BASE_VIDEO = os.path.join(BASE_DIR, "push_fatigue_3d_video.mp4")
DATA_JSON = os.path.join(BASE_DIR, "web", "data", "mtp_data.json")

SIM_DIRS = [
    os.path.join(BASE_DIR, "web", "simulations"),
    os.path.join(BASE_DIR, "public", "simulations"),
    os.path.join(BASE_DIR, "docs", "simulations"),
]

N_FRAMES = 300
FPS = 30.0
SIM_DURATION_S = 10.0
TRIAL_DURATION_S = 180.0
N_WINDOWS = 36

# Font paths (Windows standard fonts with clean fallbacks)
def _load_font(candidates, size):
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

SANS_REG = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]
SANS_BOLD = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]
MONO_REG = ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf"]

FONT_TITLE = _load_font(SANS_BOLD, 16)
FONT_SUBTITLE = _load_font(SANS_BOLD, 12)
FONT_LABEL = _load_font(SANS_BOLD, 13)
FONT_METRIC = _load_font(SANS_REG, 12)
FONT_SMALL = _load_font(SANS_REG, 11)
FONT_TINY = _load_font(SANS_REG, 10)
FONT_BADGE = _load_font(SANS_BOLD, 12)
FONT_MONO = _load_font(MONO_REG, 11)


def _text_feature(img_bgr):
    b = img_bgr[:, :, 0].astype(np.float32)
    g = img_bgr[:, :, 1].astype(np.float32)
    r = img_bgr[:, :, 2].astype(np.float32)
    lum = (r + g + b) / 3.0
    sat = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
    return np.clip(lum - 1.5 * sat, 0, 255).astype(np.uint8)


def load_base_frames_and_track():
    if not os.path.exists(BASE_VIDEO):
        raise FileNotFoundError(f"Base video not found: {BASE_VIDEO}")

    cap = cv2.VideoCapture(BASE_VIDEO)
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()

    if not frames:
        raise RuntimeError("Failed to read frames from base video.")

    # Track Dead Weight badge across all frames using bright neutral text feature
    tmpl = _text_feature(frames[0][528:543, 720:916])
    badge_positions = []
    for f in frames:
        roi = _text_feature(f[440:575, 650:1180])
        res = cv2.matchTemplate(roi, tmpl, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        bx = 650 + max_loc[0]
        by = 440 + max_loc[1]
        badge_positions.append((bx, by))

    # Mild temporal median smoothing on frames 1..N-1 (keep frame 0 exact)
    xs = np.array([p[0] for p in badge_positions], dtype=np.float64)
    ys = np.array([p[1] for p in badge_positions], dtype=np.float64)
    if len(xs) > 5:
        xs_s = xs.copy()
        ys_s = ys.copy()
        for i in range(2, len(xs) - 1):
            xs_s[i] = np.median(xs[i - 1 : i + 2])
            ys_s[i] = np.median(ys[i - 1 : i + 2])
        badge_positions = [(int(round(xs_s[i])), int(round(ys_s[i]))) for i in range(len(xs))]

    return frames, badge_positions


def fatigue_color(pct):
    """Map 0..100 fatigue % to green -> amber -> red RGB tuple."""
    p = max(0.0, min(100.0, pct)) / 100.0
    if p < 0.5:
        t = p / 0.5
        r = int(34 + (245 - 34) * t)
        g = int(197 + (158 - 197) * t)
        b = int(94 + (11 - 94) * t)
    else:
        t = (p - 0.5) / 0.5
        r = int(245 + (239 - 245) * t)
        g = int(158 + (68 - 158) * t)
        b = int(11 + (68 - 11) * t)
    return (r, g, b)


def compute_trial_curves(subj_data, mass_kg, n_frames):
    """Interpolate 36-window RMS & MDF across n_frames and compute fatigue trajectories."""
    t_windows = np.array([(i * 5.0 + 2.5) for i in range(N_WINDOWS)], dtype=np.float64)
    t_frames = np.linspace(0.0, TRIAL_DURATION_S, n_frames)

    b_rms_raw = np.array(subj_data["biceps"]["rms_series"], dtype=np.float64)
    t_rms_raw = np.array(subj_data["triceps"]["rms_series"], dtype=np.float64)
    b_mdf_raw = np.array(subj_data["biceps"]["mdf_series"], dtype=np.float64)
    t_mdf_raw = np.array(subj_data["triceps"]["mdf_series"], dtype=np.float64)

    # Interpolate RMS & MDF to frame resolution
    b_rms_f = np.interp(t_frames, t_windows, b_rms_raw)
    t_rms_f = np.interp(t_frames, t_windows, t_rms_raw)
    b_mdf_f = np.interp(t_frames, t_windows, b_mdf_raw)
    t_mdf_f = np.interp(t_frames, t_windows, t_mdf_raw)

    # Compute smooth physiological fatigue progression (0..100%)
    def calc_fatigue_series(rms_arr, mdf_arr, mdf_raw_w, rms_total):
        valid_w = mdf_raw_w[mdf_raw_w > 0]
        init_mdf = float(np.mean(valid_w[:3])) if len(valid_w) >= 3 else (float(valid_w[0]) if len(valid_w) else 80.0)
        # Active trial fraction (in case trial ends early with zeros)
        nonzero_idx = np.where(mdf_raw_w > 0)[0]
        last_active_t = t_windows[nonzero_idx[-1]] + 2.5 if len(nonzero_idx) else TRIAL_DURATION_S

        # Sustained effort factor scales with muscle RMS and load
        effort_cap = min(85.0, max(12.0, (rms_total / 68.0) * 65.0 + (mass_kg / 10.0) * 18.0))
        fat_arr = np.zeros(n_frames, dtype=np.float64)
        for i, tf in enumerate(t_frames):
            prog = min(1.0, tf / max(1.0, last_active_t))
            # Instantaneous MDF drop relative to baseline
            cur_mdf = mdf_arr[i]
            if cur_mdf <= 1.0:
                # Signal dropped to zero (exhaustion limit reached)
                mdf_contrib = 30.0
                prog = 1.0
            else:
                drop_frac = max(0.0, (init_mdf - cur_mdf) / max(1.0, init_mdf))
                mdf_contrib = min(35.0, drop_frac * 120.0)
            fat_arr[i] = min(98.0, effort_cap * (prog ** 0.95) + mdf_contrib * (0.4 + 0.6 * prog))
            if i > 0:
                # Smooth monotonic fatigue accumulation
                fat_arr[i] = max(fat_arr[i - 1], 0.85 * fat_arr[i - 1] + 0.15 * fat_arr[i])
        return np.clip(fat_arr, 0.0, 99.0)

    t_fat_f = calc_fatigue_series(t_rms_f, t_mdf_f, t_mdf_raw, subj_data["total_triceps_rms"])
    b_fat_f = calc_fatigue_series(b_rms_f, b_mdf_f, b_mdf_raw, subj_data["total_biceps_rms"])

    return {
        "t_windows": t_windows,
        "t_frames": t_frames,
        "b_rms_w": b_rms_raw,
        "t_rms_w": t_rms_raw,
        "b_mdf_w": b_mdf_raw,
        "t_mdf_w": t_mdf_raw,
        "b_rms_f": b_rms_f,
        "t_rms_f": t_rms_f,
        "b_mdf_f": b_mdf_f,
        "t_mdf_f": t_mdf_f,
        "b_fat_f": b_fat_f,
        "t_fat_f": t_fat_f,
    }


def draw_hud_and_charts_pil(
    frame_rgb,
    frame_idx,
    n_frames,
    load_label,
    mass_kg,
    subj_id,
    display_name,
    ratio_tb,
    b_drop_pct,
    t_drop_pct,
    curves,
    badge_xy,
):
    """Composite HUD card, Live RMS/MDF Simulation Panel, and Dead Weight badge onto an RGB frame."""
    h, w, _ = frame_rgb.shape
    base_img = Image.fromarray(frame_rgb).convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    t_sim = (frame_idx / max(1, n_frames - 1)) * SIM_DURATION_S
    t_trial = curves["t_frames"][frame_idx]
    t_rms = curves["t_rms_f"][frame_idx]
    b_rms = curves["b_rms_f"][frame_idx]
    t_mdf = curves["t_mdf_f"][frame_idx]
    b_mdf = curves["b_mdf_f"][frame_idx]
    t_fat = curves["t_fat_f"][frame_idx]
    b_fat = curves["b_fat_f"][frame_idx]

    # ── 1. CLEAN BACKGROUND PATCH OVER ORIGINAL TOP-LEFT HUD (15..365, 15..235)
    # Erase original HUD directly on base_img before compositing translucent card
    base_draw = ImageDraw.Draw(base_img)
    base_draw.rectangle([15, 15, 368, 232], fill=(12, 15, 22, 255))

    # Draw upgraded Top-Left HUD Card (18..388, 18..236)
    hx0, hy0, hx1, hy1 = 18, 18, 388, 236
    draw.rounded_rectangle(
        [hx0, hy0, hx1, hy1],
        radius=10,
        fill=(15, 22, 36, 245),
        outline=(62, 78, 104, 255),
        width=1,
    )

    # Title & Subject Subtitle
    draw.text((32, 27), f"3D Push Fatigue Simulation ({load_label})", font=FONT_TITLE, fill=(248, 250, 252, 255))
    draw.text(
        (32, 48),
        f"Subject: {display_name} ({subj_id.upper()})  |  Load Cell: {load_label}",
        font=FONT_SUBTITLE,
        fill=(125, 211, 252, 255),
    )

    # Triceps row + bar
    draw.text((32, 72), f"Triceps (Primary): {t_fat:.0f}%", font=FONT_LABEL, fill=(252, 165, 165, 255))
    t_mdf_txt = f"{t_mdf:.0f} Hz" if t_mdf > 1.0 else "0 Hz"
    draw.text((210, 73), f"RMS {t_rms:.1f}  |  MDF {t_mdf_txt}", font=FONT_METRIC, fill=(226, 232, 240, 255))
    bar_x0, bar_x1 = 32, 372
    draw.rounded_rectangle([bar_x0, 93, bar_x1, 104], radius=5, fill=(38, 48, 66, 255))
    fill_w_t = max(6, int((bar_x1 - bar_x0) * (t_fat / 100.0)))
    tc = fatigue_color(t_fat)
    draw.rounded_rectangle([bar_x0, 93, bar_x0 + fill_w_t, 104], radius=5, fill=(*tc, 255))

    # Biceps row + bar
    draw.text((32, 114), f"Biceps (Secondary): {b_fat:.0f}%", font=FONT_LABEL, fill=(134, 239, 172, 255))
    b_mdf_txt = f"{b_mdf:.0f} Hz" if b_mdf > 1.0 else "0 Hz"
    draw.text((210, 115), f"RMS {b_rms:.1f}  |  MDF {b_mdf_txt}", font=FONT_METRIC, fill=(226, 232, 240, 255))
    draw.rounded_rectangle([bar_x0, 135, bar_x1, 146], radius=5, fill=(38, 48, 66, 255))
    fill_w_b = max(6, int((bar_x1 - bar_x0) * (b_fat / 100.0)))
    bc = fatigue_color(b_fat)
    draw.rounded_rectangle([bar_x0, 135, bar_x0 + fill_w_b, 146], radius=5, fill=(*bc, 255))

    # Divider line
    draw.line([(32, 158), (372, 158)], fill=(45, 58, 80, 220), width=1)

    # Physics & Biomechanics Summary
    gravity_n = mass_kg * 9.81
    draw.text((32, 166), f"Gravity: {gravity_n:.1f} N", font=FONT_SMALL, fill=(250, 204, 21, 255))
    draw.text((140, 166), "Drag: 4.4 N", font=FONT_SMALL, fill=(251, 146, 60, 255))
    draw.text((236, 166), f"T/B Ratio: {ratio_tb:.2f}x", font=FONT_SMALL, fill=(96, 165, 250, 255))

    # Trial & Sim Time + Fatigue Shift
    draw.text(
        (32, 187),
        f"Trial: {t_trial:5.1f}s / 180.0s   |   Sim: {t_sim:4.1f}s / 10.0s",
        font=FONT_SMALL,
        fill=(203, 213, 225, 255),
    )
    t_drop_str = f"{t_drop_pct:+.1f}%" if t_drop_pct != 0 else "0.0%"
    b_drop_str = f"{b_drop_pct:+.1f}%" if b_drop_pct != 0 else "0.0%"
    draw.text(
        (32, 207),
        f"MDF Shift -> Triceps: {t_drop_str}   |   Biceps: {b_drop_str}",
        font=FONT_SMALL,
        fill=(148, 163, 184, 255),
    )

    # ── 2. TOP-RIGHT LIVE RMS & MDF SIMULATION PANEL (838..1262, 18..264)
    px0, py0, px1, py1 = 838, 18, 1262, 264
    draw.rounded_rectangle(
        [px0, py0, px1, py1],
        radius=10,
        fill=(15, 22, 36, 232),
        outline=(62, 78, 104, 255),
        width=1,
    )

    draw.text((px0 + 14, py0 + 10), "LIVE EMG SIMULATION (RMS & MDF)", font=FONT_SUBTITLE, fill=(248, 250, 252, 255))
    # Mini legend top-right of panel
    draw.ellipse([px1 - 140, py0 + 13, px1 - 132, py0 + 21], fill=(248, 113, 113, 255))
    draw.text((px1 - 128, py0 + 10), "Triceps", font=FONT_TINY, fill=(252, 165, 165, 255))
    draw.ellipse([px1 - 74, py0 + 13, px1 - 66, py0 + 21], fill=(96, 165, 250, 255))
    draw.text((px1 - 62, py0 + 10), "Biceps", font=FONT_TINY, fill=(147, 197, 253, 255))

    # Plot helper
    def draw_mini_chart(cx0, cy0, cx1, cy1, title, unit, t_arr, y1_arr, y2_arr, cur_t, cur_y1, cur_y2, c1, c2):
        # Chart box
        draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=6, fill=(11, 16, 27, 220), outline=(40, 52, 74, 255), width=1)
        draw.text((cx0 + 8, cy0 + 4), title, font=FONT_TINY, fill=(148, 163, 184, 255))
        draw.text(
            (cx1 - 154, cy0 + 4),
            f"T: {cur_y1:5.1f}  B: {cur_y2:5.1f} {unit}",
            font=FONT_TINY,
            fill=(226, 232, 240, 255),
        )

        gx0, gy0, gx1, gy1 = cx0 + 32, cy0 + 20, cx1 - 10, cy1 - 14
        # Grid lines
        for frac in [0.0, 0.5, 1.0]:
            gy = int(gy1 - frac * (gy1 - gy0))
            draw.line([(gx0, gy), (gx1, gy)], fill=(35, 45, 65, 180), width=1)

        y_max = max(float(np.max(y1_arr)), float(np.max(y2_arr)), 10.0) * 1.15
        y_min = 0.0
        if unit == "Hz":
            pos_vals = np.concatenate([y1_arr[y1_arr > 0], y2_arr[y2_arr > 0]])
            if len(pos_vals) > 0:
                y_min = max(0.0, float(np.min(pos_vals)) * 0.75)
                if np.min(y1_arr) == 0 or np.min(y2_arr) == 0:
                    y_min = 0.0
                y_max = float(np.max(pos_vals)) * 1.12

        draw.text((cx0 + 4, gy0 - 5), f"{int(round(y_max))}", font=FONT_TINY, fill=(100, 116, 139, 255))
        draw.text((cx0 + 4, gy1 - 7), f"{int(round(y_min))}", font=FONT_TINY, fill=(100, 116, 139, 255))

        def to_px(t_val, y_val):
            px = gx0 + (t_val / TRIAL_DURATION_S) * (gx1 - gx0)
            norm = (y_val - y_min) / max(1e-6, (y_max - y_min))
            norm = max(0.0, min(1.0, norm))
            py = gy1 - norm * (gy1 - gy0)
            return (px, py)

        # Ghost full curves (dimmed)
        pts1_all = [to_px(t_arr[k], y1_arr[k]) for k in range(len(t_arr))]
        pts2_all = [to_px(t_arr[k], y2_arr[k]) for k in range(len(t_arr))]
        if len(pts1_all) >= 2:
            draw.line(pts2_all, fill=(*c2, 55), width=1)
            draw.line(pts1_all, fill=(*c1, 55), width=1)

        # Active progressed curves up to cur_t
        active_idx = [k for k in range(len(t_arr)) if t_arr[k] <= cur_t]
        pts2_act = [to_px(t_arr[k], y2_arr[k]) for k in active_idx] + [to_px(cur_t, cur_y2)]
        pts1_act = [to_px(t_arr[k], y1_arr[k]) for k in active_idx] + [to_px(cur_t, cur_y1)]

        # Vertical playhead
        cur_px, cur_py1 = to_px(cur_t, cur_y1)
        _, cur_py2 = to_px(cur_t, cur_y2)
        draw.line([(cur_px, gy0), (cur_px, gy1)], fill=(255, 255, 255, 70), width=1)

        if len(pts2_act) >= 2:
            draw.line(pts2_act, fill=(*c2, 245), width=2)
        if len(pts1_act) >= 2:
            draw.line(pts1_act, fill=(*c1, 245), width=2)

        # Live glowing cursor dots
        draw.ellipse([cur_px - 4, cur_py2 - 4, cur_px + 4, cur_py2 + 4], fill=(*c2, 255), outline=(255, 255, 255, 220))
        draw.ellipse([cur_px - 4, cur_py1 - 4, cur_px + 4, cur_py1 + 4], fill=(*c1, 255), outline=(255, 255, 255, 220))

    draw_mini_chart(
        px0 + 12,
        py0 + 34,
        px1 - 12,
        py0 + 134,
        "RMS Activity",
        "ADC",
        curves["t_windows"],
        curves["t_rms_w"],
        curves["b_rms_w"],
        t_trial,
        t_rms,
        b_rms,
        (248, 113, 113),  # Triceps red
        (96, 165, 250),   # Biceps blue
    )

    draw_mini_chart(
        px0 + 12,
        py0 + 142,
        px1 - 12,
        py1 - 10,
        "MDF Fatigue",
        "Hz",
        curves["t_windows"],
        curves["t_mdf_w"],
        curves["b_mdf_w"],
        t_trial,
        t_mdf,
        b_mdf,
        (251, 146, 60),   # Triceps orange-red
        (56, 189, 248),   # Biceps cyan-blue
    )

    # ── 3. DEAD WEIGHT BADGE REPLACEMENT (tracked per frame)
    bx, by = badge_xy
    badge_text = f"Dead Weight ({load_label}) — Horiz. Only"
    bbox = draw.textbbox((0, 0), badge_text, font=FONT_BADGE)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    # Center around original badge center (original text box ~196x15)
    cx = bx + 98
    cy = by + 7
    pad_x, pad_y = 10, 5
    rx0 = max(640, int(cx - tw / 2 - pad_x))
    rx1 = min(1265, int(cx + tw / 2 + pad_x))
    ry0 = int(cy - th / 2 - pad_y)
    ry1 = int(cy + th / 2 + pad_y)
    # Cover original badge cleanly (min width 212px so old "(7.5 kg)" never peeks out)
    cover_x0 = min(rx0, bx - 10)
    cover_x1 = max(rx1, bx + 206)
    cover_y0 = min(ry0, by - 6)
    cover_y1 = max(ry1, by + 22)

    draw.rounded_rectangle(
        [cover_x0, cover_y0, cover_x1, cover_y1],
        radius=6,
        fill=(18, 24, 36, 242),
        outline=(92, 108, 130, 230),
        width=1,
    )
    draw.text((cx - tw / 2, cy - th / 2 - 2), badge_text, font=FONT_BADGE, fill=(241, 245, 249, 255))

    composited = Image.alpha_composite(base_img, overlay).convert("RGB")
    return np.array(composited)


def render_simulation_video(base_frames, badge_positions, load_id, load_label, mass_kg, subj_id, subj_data, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    n_frames = len(base_frames)
    curves = compute_trial_curves(subj_data, mass_kg, n_frames)

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", "1280x720",
        "-pix_fmt", "rgb24",
        "-r", "30",
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "24",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-loglevel", "error",
        out_path,
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i, bgr in enumerate(base_frames):
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            out_rgb = draw_hud_and_charts_pil(
                frame_rgb=rgb,
                frame_idx=i,
                n_frames=n_frames,
                load_label=load_label,
                mass_kg=mass_kg,
                subj_id=subj_id,
                display_name=subj_data["display_name"],
                ratio_tb=subj_data["triceps_biceps_ratio"],
                b_drop_pct=subj_data["biceps"]["mdf_drop_pct"],
                t_drop_pct=subj_data["triceps"]["mdf_drop_pct"],
                curves=curves,
                badge_xy=badge_positions[i],
            )
            proc.stdin.write(out_rgb.tobytes())
        proc.stdin.close()
        ret = proc.wait()
        if ret != 0:
            raise RuntimeError(f"ffmpeg exited with code {ret}")
    except Exception:
        proc.kill()
        raise


LOAD_LABELS = {"2.5kg": "2.5 kg", "5kg": "5.0 kg", "7.5kg": "7.5 kg", "10kg": "10.0 kg"}


def generate_single(load_id, subj_id, subj_data, mass_kg):
    """Generate and mirror a 3D simulation MP4 for a single (load_id, subj_id) trial."""
    if not os.path.exists(BASE_VIDEO):
        return None
    base_frames, badge_positions = load_base_frames_and_track()
    load_label = LOAD_LABELS.get(load_id, f"{mass_kg} kg")
    primary_out = os.path.join(SIM_DIRS[0], load_id, f"{subj_id}.mp4")
    render_simulation_video(
        base_frames, badge_positions, load_id, load_label, float(mass_kg), subj_id, subj_data, primary_out
    )
    for mirror_root in SIM_DIRS[1:]:
        mirror_out = os.path.join(mirror_root, load_id, f"{subj_id}.mp4")
        os.makedirs(os.path.dirname(mirror_out), exist_ok=True)
        shutil.copy2(primary_out, mirror_out)
    return primary_out


def generate_all(only_pair=None, preview_frame_path=None):
    with open(DATA_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("Loading base 3D video & tracking Dead Weight badge...")
    t0 = time.time()
    base_frames, badge_positions = load_base_frames_and_track()
    print(f"Loaded {len(base_frames)} frames in {time.time() - t0:.1f}s")

    load_labels = LOAD_LABELS
    total = 0

    for load_id, load_obj in data["loads"].items():
        mass_kg = float(load_obj["mass_kg"])
        load_label = load_labels.get(load_id, f"{mass_kg} kg")
        for subj_id, subj_data in load_obj["subjects"].items():
            if only_pair and (load_id, subj_id) != only_pair:
                continue

            primary_out = os.path.join(SIM_DIRS[0], load_id, f"{subj_id}.mp4")
            t_start = time.time()
            render_simulation_video(
                base_frames, badge_positions, load_id, load_label, mass_kg, subj_id, subj_data, primary_out
            )
            size_mb = os.path.getsize(primary_out) / (1024 * 1024)
            print(f"  [OK] {load_id:<5} | {subj_id:<7} -> {size_mb:.2f} MB ({time.time() - t_start:.1f}s)")

            # Mirror to public/ and docs/
            for mirror_root in SIM_DIRS[1:]:
                mirror_out = os.path.join(mirror_root, load_id, f"{subj_id}.mp4")
                os.makedirs(os.path.dirname(mirror_out), exist_ok=True)
                shutil.copy2(primary_out, mirror_out)

            if preview_frame_path:
                cap = cv2.VideoCapture(primary_out)
                cap.set(cv2.CAP_PROP_POS_FRAMES, 180)
                ret, pf = cap.read()
                if ret:
                    cv2.imwrite(preview_frame_path, pf)
                cap.release()

            total += 1

    print(f"\nDone! Generated {total} simulation video(s) across {len(SIM_DIRS)} directories.")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        # Test mode: python generate_simulations.py 2.5kg balk
        generate_all(
            only_pair=(sys.argv[1], sys.argv[2]),
            preview_frame_path="C:/Users/acer/.gemini/antigravity/brain/9558b1c6-8c41-45c3-bdfe-efb14041b133/scratch/preview_sim.png",
        )
    else:
        generate_all()
