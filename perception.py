import cv2
import numpy as np

# =====================================================================
# VISION PIPELINE (Owner: @Jay)
# =====================================================================

def detect_arrow(frame):
    """
    TODO (@Jay): Implement HSV filtering for the Green/Red arrows.
    Return: "Left", "Right", or "Unknown"
    """
    # Your color masking logic here
    return "Unknown"

def count_spheres(frame):
    """
    TODO (@Jay): Implement HSV filtering and contour counting for Blue spheres.
    Return: Integer count of spheres.
    """
    # Your contour counting logic here
    return 0

def get_clue_data(frame):
    """
    Main vision wrapper called by fly.py's state machine.
    """
    if frame is None:
        return {"direction": "None", "sphere_count": 0}
        
    direction = detect_arrow(frame)
    sphere_count = count_spheres(frame)
    
    # --- THARIQ'S DASHBOARD HOOK: DO NOT REMOVE ---
    # @Jay: Once your masks are working, save your primary debug mask here 
    # so the Command Center dashboard can display it live for triage.
    # Example: cv2.imwrite("latest_mask.jpg", your_final_blue_mask)
    # ----------------------------------------------
    
    return {"direction": direction, "sphere_count": sphere_count}