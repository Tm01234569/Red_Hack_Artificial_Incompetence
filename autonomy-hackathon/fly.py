#!/usr/bin/env python3
"""
Autonomous Red Team Hack Sim solver.

Flow
----
1.  Slow-spin while scanning for BOTH green and red arrows in the same frame.
    Compare horizontal positions:  green RIGHT of red → RIGHT,  else LEFT.
    Collect 20 votes, tally majority → turn 1 direction.
2.  Rotate nose 90° to face that direction.
3.  Fly straight until blue spheres appear.
4.  Sphere count → turn 2 (even = LEFT, odd = RIGHT).
5.  Rotate 90°, charge the target vehicle.

Vehicle table
-------------
  LEFT,  LEFT  → Tank            (fly into it)
  LEFT,  RIGHT → Boat            (fly into it)
  RIGHT, LEFT  → Jet             (fly into it)
  RIGHT, RIGHT → Ice-Cream Truck (land beside it within 50 m)

Requires:
  pip install ultralytics opencv-python
"""
import asyncio
import math
import time

import cv2
import numpy as np

try:
    from ultralytics import YOLO  # type: ignore[import-untyped]
except ImportError as _e:
    raise SystemExit(
        "\n[ERROR] ultralytics not installed.\n"
        "  Run:  pip install ultralytics\n"
        f"  ({_e})"
    )

from redteam_sim import connect, read_frame

# ──────────────────────────────────────────────────────────────────────────────
# YOLO-World model
# ──────────────────────────────────────────────────────────────────────────────
print("[init] Loading YOLO-World model …")
_MODEL = YOLO("yolov8s-worldv2.pt")
_MODEL.set_classes(["green arrow", "red arrow", "blue sphere"])
YOLO_CONF = 0.10

# ──────────────────────────────────────────────────────────────────────────────
# HSV colour ranges  (OpenCV H: 0-179, S/V: 0-255)
# ──────────────────────────────────────────────────────────────────────────────
GREEN_LO  = np.array([35,  80,  80])   # wide — neon lime green
GREEN_HI  = np.array([95, 255, 255])
RED_LO1   = np.array([0,  130,  80])   # red wraps around 0 °; H<8 avoids orange
RED_HI1   = np.array([8,  255, 255])
RED_LO2   = np.array([168, 130,  80])  # H>168 on the other side of 0
RED_HI2   = np.array([179, 255, 255])
BLUE_LO   = np.array([95,  140,  30])   # S>=140 excludes washed-out sky; V low OK for dark sphere
BLUE_HI   = np.array([135, 255, 200])   # V<=200 excludes bright sky (sky V is 200+)

# ──────────────────────────────────────────────────────────────────────────────
# Detection thresholds
# ──────────────────────────────────────────────────────────────────────────────
ARROW_MIN_AREA  = 40     # px² — minimum blob to count (low for distant arrows)
CENTER_TOL_PX   = 60     # px — centred enough for approach

SPHERE_MIN_AREA = 120    # px² per blob
SPHERE_STOP     = 600    # total area to stop approach

# ──────────────────────────────────────────────────────────────────────────────
# Flight parameters
# ──────────────────────────────────────────────────────────────────────────────
CRUISE_ALT    = -5.0
SCAN_YAW_RATE = math.radians(15)   # 15 °/s scan
APPROACH_SPD  = 2.0                # m/s — slow for controlled centering
FAST_SPD      = 9.0                # m/s — vehicle charge
LAT_GAIN      = 0.8                # m/s per unit normalised lateral error
CTRL_DT       = 0.15               # seconds per control-loop tick

# ──────────────────────────────────────────────────────────────────────────────
# Display
# ──────────────────────────────────────────────────────────────────────────────
WIN = "FPV — Red Team Hack Sim"

# ──────────────────────────────────────────────────────────────────────────────
# Vehicle table
# ──────────────────────────────────────────────────────────────────────────────
VEHICLE_TABLE = {
    ("LEFT",  "LEFT"):  ("Tank",            "fly_into"),
    ("LEFT",  "RIGHT"): ("Boat",            "fly_into"),
    ("RIGHT", "LEFT"):  ("Jet",             "fly_into"),
    ("RIGHT", "RIGHT"): ("Ice-Cream Truck", "land_beside"),
}


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────
async def do(cmd):
    await (await cmd)


def get_yaw(drone) -> float:
    s = drone.get_estimated_kinematics()
    q = s["pose"]["orientation"]
    return math.atan2(
        2.0 * (q["w"] * q["z"] + q["x"] * q["y"]),
        1.0 - 2.0 * (q["y"] ** 2 + q["z"] ** 2),
    )


def cur_pos(drone):
    s = drone.get_estimated_kinematics()
    p = s["pose"]["position"]
    return p["x"], p["y"]


# ──────────────────────────────────────────────────────────────────────────────
# Vision helpers
# ──────────────────────────────────────────────────────────────────────────────
def _hsv_mask(img, lo, hi):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m   = cv2.inRange(hsv, lo, hi)
    # CLOSE with 5x5 fills small holes inside blobs.
    # OPEN with 3x3 only removes single-pixel noise — keeps small distant blobs.
    # The old 7x7 open was erasing any blob smaller than ~40 px² (distant arrows).
    kc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    ko = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m  = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kc)
    m  = cv2.morphologyEx(m, cv2.MORPH_OPEN,  ko)
    return m


def _red_mask(img):
    """Red wraps around 0° in HSV — combine both sub-ranges."""
    return cv2.bitwise_or(_hsv_mask(img, RED_LO1, RED_HI1),
                          _hsv_mask(img, RED_LO2, RED_HI2))


def _best_contour_cx(mask, min_area):
    """Return (cx, contour) of the largest contour above min_area, or None."""
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < min_area:
        return None
    M = cv2.moments(c)
    if M["m00"] == 0:
        return None
    return M["m10"] / M["m00"], c


def get_both_arrows(frame):
    """
    Detect the green arrow and the red arrow in one frame.

    Returns (green_cx, red_cx, annotated).
      green_cx / red_cx — horizontal centre pixel of each arrow, or None.
      annotated         — BGR image with boxes + direction label drawn on it.

    Direction rule (caller implements):
      green RIGHT of red  →  turn RIGHT  (green is the go signal)
      green LEFT  of red  →  turn LEFT
    """
    results   = _MODEL(frame, verbose=False, conf=YOLO_CONF)[0]
    annotated = results.plot()
    h, w      = frame.shape[:2]

    green_cx = red_cx = None
    green_area = red_area = 0.0

    # ── YOLO path ─────────────────────────────────────────────────────────────
    for box in results.boxes:
        cls_name = _MODEL.names.get(int(box.cls), "").lower()
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        area = float((x2 - x1) * (y2 - y1))
        roi  = frame[y1:y2, x1:x2]
        cx   = (x1 + x2) / 2.0

        if "green" in cls_name and area > green_area:
            if np.count_nonzero(_hsv_mask(roi, GREEN_LO, GREEN_HI)) >= area * 0.01:
                green_cx, green_area = cx, area
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

        elif "red" in cls_name and area > red_area:
            if np.count_nonzero(_red_mask(roi)) >= area * 0.01:
                red_cx, red_area = cx, area
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)

    # ── HSV fallback for green ────────────────────────────────────────────────
    if green_cx is None:
        result = _best_contour_cx(_hsv_mask(frame, GREEN_LO, GREEN_HI), ARROW_MIN_AREA)
        if result:
            gx, c = result
            green_cx = gx
            bx, by, bw, bh = cv2.boundingRect(c)
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)

    # ── HSV fallback for red ──────────────────────────────────────────────────
    if red_cx is None:
        result = _best_contour_cx(_red_mask(frame), ARROW_MIN_AREA)
        if result:
            rx, c = result
            bx, by, bw, bh = cv2.boundingRect(c)
            # Ground lines form long thin blobs; arrows are compact.
            # Reject anything with aspect ratio > 5 (longer than 5× its width).
            aspect = max(bw, bh) / max(1, min(bw, bh))
            if aspect <= 5:
                red_cx = rx
                cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 0, 255), 2)
            else:
                cv2.putText(annotated, f"red blob skip AR={aspect:.1f}", (10, h - 48),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 80, 255), 1)

    # ── Raw pixel counts (always shown for debug) ─────────────────────────────
    g_px = np.count_nonzero(_hsv_mask(frame, GREEN_LO, GREEN_HI))
    r_px = np.count_nonzero(_red_mask(frame))
    cv2.putText(annotated, f"gpx={g_px}", (10, h - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1)
    cv2.putText(annotated, f"rpx={r_px}", (10, h - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 255), 1)

    # ── Centroid dots + live direction label ──────────────────────────────────
    if green_cx is not None:
        cv2.circle(annotated, (int(green_cx), h // 2), 10, (0, 255, 0), -1)
        cv2.putText(annotated, f"G:{int(green_cx)}", (int(green_cx) - 25, h // 2 - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    if red_cx is not None:
        cv2.circle(annotated, (int(red_cx), h // 2 + 30), 10, (0, 0, 255), -1)
        cv2.putText(annotated, f"R:{int(red_cx)}", (int(red_cx) - 25, h // 2 + 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
    if green_cx is not None and red_cx is not None:
        label = "→ RIGHT" if green_cx > red_cx else "← LEFT"
        cv2.putText(annotated, label, (w // 2 - 50, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)

    return green_cx, red_cx, annotated


def _is_sphere_shaped(c) -> bool:
    """
    Return True if contour c looks like a sphere (compact, roundish).
    Rejects sky strips and ground shadows which are elongated/flat.
    """
    area = cv2.contourArea(c)
    if area < SPHERE_MIN_AREA:
        return False

    # Aspect ratio: sphere bounding box is roughly square
    _, _, bw, bh = cv2.boundingRect(c)
    aspect = max(bw, bh) / max(1, min(bw, bh))
    if aspect > 2.5:          # too elongated → not a sphere
        return False

    # Circularity: 4π·area / perimeter² ≈ 1 for a perfect circle
    perim = cv2.arcLength(c, True)
    if perim == 0:
        return False
    circularity = 4 * math.pi * area / (perim ** 2)
    if circularity < 0.4:     # sky strip, shadow, or noise → reject
        return False

    return True


def get_spheres_info(frame):
    """Returns (count, total_area, annotated). Does NOT call cv2.imshow."""
    results   = _MODEL(frame, verbose=False, conf=YOLO_CONF)[0]
    annotated = results.plot()
    h         = frame.shape[0]

    yn, ya = 0, 0.0
    for box in results.boxes:
        name = _MODEL.names[int(box.cls)].lower()
        if "sphere" in name or "ball" in name:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            box_area = float((x2 - x1) * (y2 - y1))
            if box_area < 80:
                continue
            roi = frame[y1:y2, x1:x2]
            blue_px = np.count_nonzero(_hsv_mask(roi, BLUE_LO, BLUE_HI))
            # YOLO box must have enough actual blue pixels
            if blue_px >= box_area * 0.05:
                # Also check aspect ratio of the box itself
                bw2, bh2 = x2 - x1, y2 - y1
                if max(bw2, bh2) / max(1, min(bw2, bh2)) <= 2.5:
                    yn += 1
                    ya += box_area
                    cv2.circle(annotated,
                               ((x1 + x2) // 2, (y1 + y2) // 2),
                               max(bw2, bh2) // 2, (255, 128, 0), 2)

    if yn > 0:
        cv2.putText(annotated, f"YOLO spheres: {yn}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 128, 0), 2)
        return yn, ya, annotated

    # ── HSV fallback with shape filter ───────────────────────────────────────
    bmask = _hsv_mask(frame, BLUE_LO, BLUE_HI)
    cnts, _ = cv2.findContours(bmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Show total blue px for debug
    b_px = np.count_nonzero(bmask)
    cv2.putText(annotated, f"bpx={b_px}", (10, h - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 128, 0), 1)

    valid = [c for c in cnts if _is_sphere_shaped(c)]
    total = 0.0
    for c in valid:
        area = cv2.contourArea(c)
        total += area
        bx, by, bw, bh = cv2.boundingRect(c)
        cx_s, cy_s = bx + bw // 2, by + bh // 2
        cv2.circle(annotated, (cx_s, cy_s), max(bw, bh) // 2, (255, 0, 0), 2)
        perim = cv2.arcLength(c, True)
        circ  = 4 * math.pi * area / (perim ** 2) if perim else 0
        cv2.putText(annotated, f"c={circ:.2f}", (bx, by - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

    if valid:
        cv2.putText(annotated, f"HSV spheres: {len(valid)}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
    return len(valid), total, annotated


def show(frame, label: str = ""):
    """Display frame in the FPV window. Call this every loop tick."""
    disp = frame.copy()
    if label:
        cv2.putText(disp, label, (10, disp.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    cv2.imshow(WIN, disp)
    cv2.waitKey(1)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 — Detect both arrows, vote on relative position, align yaw
# ──────────────────────────────────────────────────────────────────────────────
async def approach_and_align_arrow(drone) -> tuple[str, float]:
    """
    Returns (direction, arrow_world_yaw).

    Strategy: spin slowly while collecting frames.  Each frame where BOTH the
    green and red arrow are visible casts one vote:
        green_cx > red_cx  →  green is RIGHT of red  →  vote RIGHT
        green_cx < red_cx  →  green is LEFT  of red  →  vote LEFT
    Once 20 votes are in, stop and tally.  If spinning a full circle still
    didn't yield 20 votes, approach forward while continuing to scan.
    Finally rotate nose 90° to face the determined direction.
    """
    fh, fw = 480, 640
    last_frame = np.zeros((fh, fw, 3), dtype=np.uint8)
    votes: list[str] = []

    # ════════════════════════════════════════════════════════════════
    # STEP 0 — crawl forward to close distance before spinning.
    #           Arrows that are far away appear tiny and may be below
    #           the detection threshold.  A 6-second forward push
    #           brings them into comfortable detection range.
    # ════════════════════════════════════════════════════════════════
    print("[P1-0] Closing distance …")
    _ = await drone.move_by_velocity_body_frame_async(APPROACH_SPD, 0.0, 0.0, 6.0)
    t0 = time.time()
    while time.time() - t0 < 6.0:
        frame = read_frame(drone)
        if frame is None:
            show(last_frame, "CLOSING — waiting")
            await asyncio.sleep(0.05)
            continue
        last_frame = frame
        _, _, annotated = get_both_arrows(frame)
        show(annotated, "CLOSING distance …")
        await asyncio.sleep(0.05)
    drone.cancel_last_task()
    await asyncio.sleep(0.3)

    # ════════════════════════════════════════════════════════════════
    # STEP A — spin until the FIRST frame where BOTH arrows are
    #           visible at once, then stop immediately.
    # ════════════════════════════════════════════════════════════════
    print("[P1-A] Spinning — waiting for both arrows in frame …")
    _ = await drone.rotate_by_yaw_rate_async(SCAN_YAW_RATE, 35.0)
    t0 = time.time()
    found_both = False

    while time.time() - t0 < 35.0:
        frame = read_frame(drone)
        if frame is None:
            show(last_frame, "SCAN — waiting")
            await asyncio.sleep(0.02)
            continue

        last_frame = frame
        fh, fw = frame.shape[:2]
        green_cx, red_cx, annotated = get_both_arrows(frame)
        g_str = f"{int(green_cx)}" if green_cx is not None else "?"
        r_str = f"{int(red_cx)}"   if red_cx   is not None else "?"
        show(annotated, f"SCAN  G={g_str}  R={r_str}")

        if green_cx is not None and red_cx is not None:
            drone.cancel_last_task()   # stop spin immediately
            await asyncio.sleep(0.25)  # let rotation settle
            print("[P1-A] Both arrows in frame — stopped spin")
            found_both = True
            break

        await asyncio.sleep(0.02)

    if not found_both:
        print("[P1-A] ⚠ Full rotation without seeing both — will approach")

    # ════════════════════════════════════════════════════════════════
    # STEP B — hover and collect votes while both arrows are still
    #           in frame (drone is now stationary)
    # ════════════════════════════════════════════════════════════════
    print("[P1-B] Hovering — collecting votes …")
    t0 = time.time()

    while time.time() - t0 < 6.0 and len(votes) < 25:
        frame = read_frame(drone)
        if frame is None:
            show(last_frame, "VOTE — waiting")
            await asyncio.sleep(0.02)
            continue

        last_frame = frame
        fh, fw = frame.shape[:2]
        green_cx, red_cx, annotated = get_both_arrows(frame)
        g_str = f"{int(green_cx)}" if green_cx is not None else "?"
        r_str = f"{int(red_cx)}"   if red_cx   is not None else "?"
        show(annotated, f"VOTE  G={g_str}  R={r_str}  votes={len(votes)}")

        if green_cx is not None and red_cx is not None:
            votes.append("RIGHT" if green_cx > red_cx else "LEFT")

        await asyncio.sleep(0.02)

    print(f"[P1-B] Collected {len(votes)} votes while hovering")

    # ════════════════════════════════════════════════════════════════
    # STEP C (fallback) — if still short, approach the arrows and
    #           keep scanning until 25 votes are in
    # ════════════════════════════════════════════════════════════════
    if len(votes) < 10:
        print("[P1-C] Not enough votes — approaching arrows …")
        t0 = time.time()

        while time.time() - t0 < 30.0 and len(votes) < 25:
            frame = read_frame(drone)
            if frame is None:
                show(last_frame, "APPROACH — waiting")
                await asyncio.sleep(0.02)
                continue

            last_frame = frame
            fh, fw = frame.shape[:2]
            green_cx, red_cx, annotated = get_both_arrows(frame)
            g_str = f"{int(green_cx)}" if green_cx is not None else "?"
            r_str = f"{int(red_cx)}"   if red_cx   is not None else "?"
            show(annotated, f"APPROACH  G={g_str}  R={r_str}  votes={len(votes)}")

            if green_cx is not None and red_cx is not None:
                votes.append("RIGHT" if green_cx > red_cx else "LEFT")

            target_cx = green_cx if green_cx is not None else red_cx
            vy = LAT_GAIN * (target_cx - fw / 2) / (fw / 2) if target_cx is not None else 0.0
            drone.cancel_last_task()
            _ = await drone.move_by_velocity_body_frame_async(APPROACH_SPD, vy, 0.0, 2.0)
            await asyncio.sleep(CTRL_DT)

        drone.cancel_last_task()
        await do(drone.hover_async())
        await asyncio.sleep(0.3)

    # ════════════════════════════════════════════════════════════════
    # STEP D — tally votes
    # ════════════════════════════════════════════════════════════════
    left_count  = votes.count("LEFT")
    right_count = votes.count("RIGHT")
    if not votes:
        best_dir = "RIGHT"
        print("[P1-D] ⚠ No votes collected — defaulting RIGHT")
    else:
        best_dir = "RIGHT" if right_count >= left_count else "LEFT"
    print(f"[P1-D] Votes: LEFT={left_count}  RIGHT={right_count}  →  {best_dir}")

    # ════════════════════════════════════════════════════════════════
    # STEP E — rotate nose 90° to face the chosen direction
    # ════════════════════════════════════════════════════════════════
    current_yaw = get_yaw(drone)
    delta       = -math.pi / 2 if best_dir == "LEFT" else math.pi / 2
    arrow_yaw   = current_yaw + delta
    print(f"[P1-E] Rotating nose {best_dir} → {math.degrees(arrow_yaw):.0f}°")
    await do(drone.rotate_to_yaw_async(arrow_yaw))
    await asyncio.sleep(0.3)

    return best_dir, arrow_yaw


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 — fly in arrow direction until blue spheres appear
# ──────────────────────────────────────────────────────────────────────────────
async def find_spheres(drone) -> int:
    """Fly straight (current heading = arrow direction).  Return sphere count."""
    print("[P2] Flying in arrow direction to find spheres …")

    _ = await drone.move_by_velocity_body_frame_async(APPROACH_SPD, 0.0, 0.0, 30.0)
    t0 = time.time()
    raw_count = 0
    last_frame: np.ndarray | None = None

    while time.time() - t0 < 30.0:
        frame = read_frame(drone)
        if frame is None:
            if last_frame is not None:
                show(last_frame, "P2: seeking spheres — no frame")
            await asyncio.sleep(0.02)
            continue

        last_frame = frame
        count, area, annotated = get_spheres_info(frame)
        show(annotated, f"P2: spheres={count}  area={area:.0f}")
        if count > 0:
            raw_count = count
        if area >= SPHERE_STOP:
            print(f"[P2] Spheres visible (count={count}, area={area:.0f})")
            drone.cancel_last_task()
            await asyncio.sleep(0.25)
            break

        await asyncio.sleep(0.02)

    if raw_count == 0:
        print("[P2] Not found straight ahead — spinning …")
        _ = await drone.rotate_by_yaw_rate_async(SCAN_YAW_RATE, 32.0)
        t0 = time.time()
        while time.time() - t0 < 32.0:
            frame = read_frame(drone)
            if frame is None:
                if last_frame is not None:
                    show(last_frame, "P2 spin — no frame")
                await asyncio.sleep(0.02)
                continue
            last_frame = frame
            count, area, annotated = get_spheres_info(frame)
            show(annotated, f"P2 spin: spheres={count}  area={area:.0f}")
            if count > 0:
                raw_count = count
            if area >= SPHERE_STOP:
                drone.cancel_last_task()
                await asyncio.sleep(0.25)
                break
            await asyncio.sleep(0.02)

    # Stable median over 20 frames
    await do(drone.hover_async())
    counts = []
    for _ in range(20):
        frame = read_frame(drone)
        if frame is not None:
            last_frame = frame
            c, _, annotated = get_spheres_info(frame)
            show(annotated, f"P2 count: {c}")
            counts.append(c)
        elif last_frame is not None:
            show(last_frame, "P2 count — no frame")
        await asyncio.sleep(0.07)

    counts.sort()
    median = counts[len(counts) // 2] if counts else raw_count or 1
    if median == 0:
        median = raw_count or 1
    return median


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
async def main():
    client, world, drone = connect()
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 640, 480)

    try:
        print("=" * 58)
        print("  Red Team Hack Sim  —  Autonomous Solver  (YOLO)")
        print("=" * 58)

        # ── Arm & climb ───────────────────────────────────────────────────────
        print("\n[ARM] Taking off …")
        drone.enable_api_control()
        drone.arm()
        await do(drone.takeoff_async())
        n0, e0 = cur_pos(drone)
        await do(drone.move_to_position_async(n0, e0, CRUISE_ALT, 4.0))
        await asyncio.sleep(0.3)

        # ═════════════════════════════════════════════════════════════════════
        # PHASE 1  —  Find arrow, fly above it, align yaw
        # ═════════════════════════════════════════════════════════════════════
        turn1, arrow_yaw = await approach_and_align_arrow(drone)
        print(f"\n[P1 DONE] turn1={turn1}  yaw={math.degrees(arrow_yaw):.0f}°")

        # ═════════════════════════════════════════════════════════════════════
        # PHASE 2  —  Fly in arrow direction → count spheres
        # ═════════════════════════════════════════════════════════════════════
        sphere_count = await find_spheres(drone)
        turn2        = "LEFT" if sphere_count % 2 == 0 else "RIGHT"
        print(f"\n[P2 DONE] spheres={sphere_count}  turn2={turn2}")

        # ── Turn 2 ────────────────────────────────────────────────────────────
        yaw2 = get_yaw(drone) + (-math.pi / 2 if turn2 == "LEFT" else math.pi / 2)
        print(f"[T2] Rotating {turn2} → {math.degrees(yaw2):.0f}°")
        await do(drone.rotate_to_yaw_async(yaw2))
        await asyncio.sleep(0.2)

        # ═════════════════════════════════════════════════════════════════════
        # PHASE 3  —  Charge target vehicle
        # ═════════════════════════════════════════════════════════════════════
        vehicle_name, interaction = VEHICLE_TABLE[(turn1, turn2)]
        print(f"\n[P3] Target → {vehicle_name}  ({interaction})")

        if interaction == "fly_into":
            await do(drone.move_by_velocity_body_frame_async(FAST_SPD, 0.0, 0.0, 14.0))
            print(f"[P3] ✓  Struck {vehicle_name}!")
        else:
            await do(drone.move_by_velocity_body_frame_async(APPROACH_SPD, 0.0, 0.0, 10.0))
            n, e = cur_pos(drone)
            await do(drone.move_to_position_async(n, e, -1.2, 2.0))
            await do(drone.land_async())
            print("[P3] ✓  Landed beside Ice-Cream Truck!")

        # ── Result ────────────────────────────────────────────────────────────
        deadline = time.time() + 8.0
        while time.time() < deadline:
            try:
                state   = world.get_object_float_property("RaceManager", "MissionState")
                elapsed = world.get_object_float_property("RaceManager", "ElapsedSeconds")
                if state == 2:
                    print(f"✅  MISSION PASSED — {elapsed:.1f} s"); break
                if state == 3:
                    print(f"❌  FAILED — {elapsed:.1f} s");         break
            except Exception:
                pass
            await asyncio.sleep(0.25)
        else:
            print("[RESULT] Check the in-game screen")

    finally:
        cv2.destroyAllWindows()
        client.disconnect()
        print("[DONE] Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
