#!/usr/bin/env python3
"""
Autonomous Red Team Hack Sim solver.

Detection : YOLO-World ("green arrow" / "blue sphere") with HSV colour fallback.
Navigation: continuous velocity / yaw-rate commands – cancel_last_task() the
            moment detection is confident enough.  No step-and-halt loops.
Display   : live OpenCV window identical to view_camera.py, with YOLO boxes.

Install once (internet required for the model weights):
    pip install ultralytics opencv-python
Then run with the sim already running:
    python fly.py

Vehicle legend
--------------
  LEFT,  LEFT  → Tank            (fly into it)
  LEFT,  RIGHT → Boat            (fly into it)
  RIGHT, LEFT  → Jet             (fly into it)
  RIGHT, RIGHT → Ice-Cream Truck (land beside it within 50 m)
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
        "\n[ERROR] ultralytics is not installed.\n"
        "  Run:  pip install ultralytics\n"
        f"  ({_e})"
    )

from redteam_sim import connect, read_frame

# ──────────────────────────────────────────────────────────────────────────────
# YOLO-World model  (auto-downloads ~50 MB on first run)
# ──────────────────────────────────────────────────────────────────────────────
print("[init] Loading YOLO-World model …")
_MODEL = YOLO("yolov8s-worldv2.pt")
_MODEL.set_classes(["green arrow", "blue sphere"])
YOLO_CONF = 0.25          # detection confidence threshold

# ──────────────────────────────────────────────────────────────────────────────
# HSV colour ranges – used as fallback & for direction / colour validation
# ──────────────────────────────────────────────────────────────────────────────
GREEN_LO = np.array([35,  65,  65])
GREEN_HI = np.array([85, 255, 255])

BLUE_LO  = np.array([100,  90,  55])
BLUE_HI  = np.array([135, 255, 255])

# ──────────────────────────────────────────────────────────────────────────────
# Detection thresholds  (px² of bounding box – proxy for distance)
# ──────────────────────────────────────────────────────────────────────────────
ARROW_SPIN_STOP   = 400    # stop spinning when arrow is visible this size
ARROW_FLY_STOP    = 2800   # stop flying-in when arrow fills this much
SPHERE_SPIN_STOP  = 300    # stop spinning when any sphere is this size
SPHERE_FLY_STOP   = 600    # stop flying-in when spheres fill this much

# ──────────────────────────────────────────────────────────────────────────────
# Flight parameters
# ──────────────────────────────────────────────────────────────────────────────
CRUISE_ALT   = -5.0          # 5 m AGL (NED: up is negative)
SCAN_YAW_RATE = math.radians(30)   # 30 °/s — one full 360° in 12 s
APPROACH_SPD  = 6.0          # m/s toward detected target
FAST_SPD      = 9.0          # m/s for final vehicle charge

# ──────────────────────────────────────────────────────────────────────────────
# Display window  (mirrors view_camera.py)
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
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
async def do(cmd):
    """Double-await: blocks until the maneuver completes."""
    await (await cmd)


def get_yaw(drone) -> float:
    """Estimated yaw in radians (NED: 0=North, +π/2=East)."""
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
# Vision
# ──────────────────────────────────────────────────────────────────────────────
def _hsv_mask(img, lo, hi):
    """HSV threshold + morphological clean-up on an image or ROI."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m   = cv2.inRange(hsv, lo, hi)
    k   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    m   = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
    m   = cv2.morphologyEx(m, cv2.MORPH_OPEN,  k)
    return m


def _arrow_direction_from_mask(mask):
    """
    Pixel-column analysis on a binary mask.
    Shaft side has more pixels than arrowhead side:
      →  left_px > right_px  → direction = RIGHT
      ←  right_px > left_px  → direction = LEFT
    """
    mid      = mask.shape[1] // 2
    left_px  = int(np.count_nonzero(mask[:, :mid]))
    right_px = int(np.count_nonzero(mask[:, mid:]))
    return "RIGHT" if left_px > right_px else "LEFT"


def detect_arrow(frame):
    """
    Detect the green arrow in `frame`.

    Primary  : YOLO-World ("green arrow") + HSV green validation on the box.
    Fallback : full-frame HSV green mask.
    Display  : shows annotated frame in the live window.

    Returns (direction, area):
        direction – "LEFT" | "RIGHT" | None
        area      – bounding-box px² (proxy for distance)
    """
    results  = _MODEL(frame, verbose=False, conf=YOLO_CONF)[0]
    annotated = results.plot()

    # ── YOLO path ────────────────────────────────────────────────────────────
    best_box, best_area = None, 0.0
    for box in results.boxes:
        name = _MODEL.names[int(box.cls)].lower()
        if "arrow" in name:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            area = float((x2 - x1) * (y2 - y1))
            if area > best_area:
                best_area, best_box = area, (x1, y1, x2, y2)

    if best_box:
        x1, y1, x2, y2 = best_box
        roi        = frame[y1:y2, x1:x2]
        green_mask = _hsv_mask(roi, GREEN_LO, GREEN_HI)
        # Require at least 5 % green pixels inside the box to call it genuine
        if np.count_nonzero(green_mask) >= (x2 - x1) * (y2 - y1) * 0.05:
            direction = _arrow_direction_from_mask(green_mask)
            cv2.putText(annotated, f"YOLO arrow: {direction}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow(WIN, annotated); cv2.waitKey(1)
            return direction, best_area

    # ── HSV fallback ─────────────────────────────────────────────────────────
    green_mask = _hsv_mask(frame, GREEN_LO, GREEN_HI)
    cnts, _    = cv2.findContours(green_mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        c    = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(c)
        if area > 400:
            x, y, w, h = cv2.boundingRect(c)
            roi_mask   = green_mask[y:y + h, x:x + w]
            direction  = _arrow_direction_from_mask(roi_mask)
            debug      = annotated.copy()
            cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(debug, f"HSV arrow: {direction}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow(WIN, debug); cv2.waitKey(1)
            return direction, float(area)

    cv2.imshow(WIN, annotated); cv2.waitKey(1)
    return None, 0.0


def detect_spheres(frame):
    """
    Count blue spheres in `frame`.

    Primary  : YOLO-World ("blue sphere") + HSV blue validation.
    Fallback : full-frame HSV blue blob count.
    Display  : annotated frame in live window.

    Returns (count, total_area).
    """
    results   = _MODEL(frame, verbose=False, conf=YOLO_CONF)[0]
    annotated = results.plot()

    # ── YOLO path ────────────────────────────────────────────────────────────
    yolo_count, yolo_area = 0, 0.0
    for box in results.boxes:
        name = _MODEL.names[int(box.cls)].lower()
        if "sphere" in name or "ball" in name:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            area = float((x2 - x1) * (y2 - y1))
            if area < 100:
                continue
            roi       = frame[y1:y2, x1:x2]
            blue_mask = _hsv_mask(roi, BLUE_LO, BLUE_HI)
            if np.count_nonzero(blue_mask) >= area * 0.05:
                yolo_count += 1
                yolo_area  += area

    if yolo_count > 0:
        cv2.putText(annotated, f"YOLO spheres: {yolo_count}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 128, 0), 2)
        cv2.imshow(WIN, annotated); cv2.waitKey(1)
        return yolo_count, yolo_area

    # ── HSV fallback ─────────────────────────────────────────────────────────
    blue_mask = _hsv_mask(frame, BLUE_LO, BLUE_HI)
    cnts, _   = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL,
                                  cv2.CHAIN_APPROX_SIMPLE)
    valid     = [c for c in cnts if cv2.contourArea(c) > 150]
    if valid:
        debug = annotated.copy()
        for c in valid:
            x, y, w, h = cv2.boundingRect(c)
            cv2.rectangle(debug, (x, y), (x + w, y + h), (255, 0, 0), 2)
        cv2.putText(debug, f"HSV spheres: {len(valid)}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
        cv2.imshow(WIN, debug); cv2.waitKey(1)
        return len(valid), sum(cv2.contourArea(c) for c in valid)

    cv2.imshow(WIN, annotated); cv2.waitKey(1)
    return 0, 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Continuous-flight search routines
# ──────────────────────────────────────────────────────────────────────────────
async def spin_until(drone, check_fn, stop_area: float,
                     yaw_rate: float = SCAN_YAW_RATE, max_sec: float = 13.0):
    """
    Rotate continuously at `yaw_rate` rad/s.
    Calls check_fn(frame) → (result, area) on every frame.
    Cancels the spin and returns (result, area) the instant area >= stop_area.
    If the full rotation completes without a hit, returns the best seen.
    """
    _ = await drone.rotate_by_yaw_rate_async(yaw_rate, max_sec)
    best_r, best_a = None, 0.0
    t0           = time.time()

    while time.time() - t0 < max_sec:
        frame = read_frame(drone)
        if frame is not None:
            r, a = check_fn(frame)
            if a > best_a:
                best_a, best_r = a, r
            if r is not None and a >= stop_area:
                drone.cancel_last_task()
                await asyncio.sleep(0.25)
                return best_r, best_a
        await asyncio.sleep(0.02)

    await asyncio.sleep(0.15)
    return best_r, best_a


async def fly_until(drone, check_fn, stop_area: float,
                    speed: float = APPROACH_SPD, max_sec: float = 30.0):
    """
    Fly forward in body frame continuously at `speed` m/s.
    Cancels flight and returns when check_fn reports area >= stop_area.
    """
    _ = await drone.move_by_velocity_body_frame_async(speed, 0.0, 0.0, max_sec)
    best_r, best_a = None, 0.0
    t0           = time.time()

    while time.time() - t0 < max_sec:
        frame = read_frame(drone)
        if frame is not None:
            r, a = check_fn(frame)
            if a > best_a:
                best_a, best_r = a, r
            if r is not None and a >= stop_area:
                drone.cancel_last_task()
                await asyncio.sleep(0.25)
                return best_r, best_a
        await asyncio.sleep(0.02)

    return best_r, best_a


async def majority_vote_arrow(drone, n: int = 15, delay: float = 0.06):
    """Hover and return the majority-voted arrow direction over n frames."""
    await do(drone.hover_async())
    votes: dict[str, int] = {}
    for _ in range(n):
        frame = read_frame(drone)
        if frame is not None:
            d, _ = detect_arrow(frame)
            if d:
                votes[d] = votes.get(d, 0) + 1
        await asyncio.sleep(delay)
    return max(votes, key=votes.get) if votes else None


async def median_sphere_count(drone, n: int = 20, delay: float = 0.06):
    """Hover and return the median sphere count over n frames."""
    await do(drone.hover_async())
    counts = []
    for _ in range(n):
        frame = read_frame(drone)
        if frame is not None:
            c, _ = detect_spheres(frame)
            counts.append(c)
        await asyncio.sleep(delay)
    if not counts:
        return 0
    counts.sort()
    return counts[len(counts) // 2]


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
async def main():
    client, world, drone = connect()
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 640, 480)

    try:
        print("=" * 56)
        print("  Red Team Hack Sim  —  Autonomous Solver  (YOLO)")
        print("=" * 56)

        # ── Arm & climb ───────────────────────────────────────────────────────
        print("\n[ARM] Taking off …")
        drone.enable_api_control()
        drone.arm()
        await do(drone.takeoff_async())
        n0, e0 = cur_pos(drone)
        await do(drone.move_to_position_async(n0, e0, CRUISE_ALT, 4.0))
        await asyncio.sleep(0.3)

        # ═════════════════════════════════════════════════════════════════════
        # PHASE 1  —  Locate and read the green arrow
        # ═════════════════════════════════════════════════════════════════════
        print("\n[P1] Spinning to locate green arrow …")
        _, spin_area = await spin_until(drone, detect_arrow, ARROW_SPIN_STOP)

        if spin_area >= ARROW_SPIN_STOP:
            # Arrow is visible; fly toward it until it fills the frame
            print(f"[P1] Arrow spotted (area={spin_area:.0f}) — flying in …")
            await fly_until(drone, detect_arrow, ARROW_FLY_STOP, speed=APPROACH_SPD)
        else:
            print("[P1] Weak signal — trying a second sweep 2 m higher …")
            n, e = cur_pos(drone)
            await do(drone.move_to_position_async(n, e, CRUISE_ALT - 2.0, 2.0))
            _, spin_area2 = await spin_until(drone, detect_arrow, ARROW_SPIN_STOP)
            if spin_area2 >= ARROW_SPIN_STOP:
                await fly_until(drone, detect_arrow, ARROW_FLY_STOP, speed=APPROACH_SPD)

        # Stable majority vote for direction
        turn1 = await majority_vote_arrow(drone)
        if turn1 is None:
            turn1 = "RIGHT"
            print("[P1] ⚠ No direction detected — defaulting to RIGHT")

        print(f"[P1] ✓  Green arrow direction = {turn1}   (TURN 1 = {turn1})")

        # ── Turn 1: rotate 90° relative to current heading ───────────────────
        yaw1 = get_yaw(drone) + (-math.pi / 2 if turn1 == "LEFT" else math.pi / 2)
        print(f"[T1] Rotating {turn1} → yaw = {math.degrees(yaw1):.0f}°")
        await do(drone.rotate_to_yaw_async(yaw1))
        await asyncio.sleep(0.2)

        # ═════════════════════════════════════════════════════════════════════
        # PHASE 2  —  Locate and count the blue spheres
        # ═════════════════════════════════════════════════════════════════════
        def _sphere_check(frame):
            count, area = detect_spheres(frame)
            return (count if count > 0 else None), area

        print("\n[P2] Flying forward to find blue spheres …")
        raw_count, sphere_area = await fly_until(
            drone, _sphere_check, SPHERE_FLY_STOP,
            speed=APPROACH_SPD, max_sec=20.0,
        )

        if sphere_area < SPHERE_SPIN_STOP:
            print("[P2] Spheres not ahead — spinning to search …")
            raw_count, sphere_area = await spin_until(
                drone, _sphere_check, SPHERE_SPIN_STOP)
            if sphere_area >= SPHERE_SPIN_STOP:
                await fly_until(drone, _sphere_check, SPHERE_FLY_STOP,
                                speed=APPROACH_SPD, max_sec=15.0)

        sphere_count = await median_sphere_count(drone)
        if sphere_count == 0:
            sphere_count = raw_count or 1
            print(f"[P2] ⚠ Median count 0 — using raw {sphere_count}")

        turn2 = "LEFT" if sphere_count % 2 == 0 else "RIGHT"
        print(f"[P2] ✓  {sphere_count} sphere(s)  →  TURN 2 = {turn2}")

        # ── Turn 2 ────────────────────────────────────────────────────────────
        yaw2 = get_yaw(drone) + (-math.pi / 2 if turn2 == "LEFT" else math.pi / 2)
        print(f"[T2] Rotating {turn2} → yaw = {math.degrees(yaw2):.0f}°")
        await do(drone.rotate_to_yaw_async(yaw2))
        await asyncio.sleep(0.2)

        # ═════════════════════════════════════════════════════════════════════
        # PHASE 3  —  Charge the target vehicle
        # ═════════════════════════════════════════════════════════════════════
        vehicle_name, interaction = VEHICLE_TABLE[(turn1, turn2)]
        print(f"\n[P3] Target → {vehicle_name}  ({interaction})")

        if interaction == "fly_into":
            print(f"[P3] Full throttle into {vehicle_name} …")
            await do(drone.move_by_velocity_body_frame_async(
                FAST_SPD, 0.0, 0.0, 14.0))
            print(f"[P3] ✓  Struck {vehicle_name}!")

        else:  # Ice-Cream Truck — must land beside it
            print("[P3] Approaching Ice-Cream Truck to land beside it …")
            await do(drone.move_by_velocity_body_frame_async(
                APPROACH_SPD, 0.0, 0.0, 10.0))
            n, e = cur_pos(drone)
            await do(drone.move_to_position_async(n, e, -1.2, 2.0))
            await do(drone.land_async())
            print("[P3] ✓  Landed beside Ice-Cream Truck!")

        # ── Poll RaceManager ──────────────────────────────────────────────────
        print("\n[RESULT] Polling …")
        deadline = time.time() + 8.0
        while time.time() < deadline:
            try:
                state   = world.get_object_float_property("RaceManager", "MissionState")
                elapsed = world.get_object_float_property("RaceManager", "ElapsedSeconds")
                if state == 2:
                    print(f"✅  MISSION PASSED — {elapsed:.1f} s")
                    break
                if state == 3:
                    print(f"❌  FAILED — {elapsed:.1f} s")
                    break
            except Exception:
                pass
            await asyncio.sleep(0.25)
        else:
            print("[RESULT] Check the in-game screen for PASSED / FAILED")

    finally:
        cv2.destroyAllWindows()
        client.disconnect()
        print("[DONE] Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
