#!/usr/bin/env python3
"""fly.py - autonomous-flight starter (SimpleFlight). Copy this and build on it.

Shows the two data sources your autonomy needs plus how to command the drone,
using the redteam_sim helper library -- all over one client connection:
  * CONTROL + TELEMETRY  via the ProjectAirSim client (arm / takeoff / move / state)
  * VIDEO                via read_frame(drone) -> BGR numpy image

Launch the game first (see README), then run this:
    python fly.py

Retry from the start line anytime from your own code:  reset(drone)
Coordinates are NED metres: +north, +east, +DOWN -- climbing is NEGATIVE z.
"""

#!/usr/bin/env python3
import asyncio
import json
import os
from redteam_sim import connect, reset, read_frame
from perception import get_clue_data

# =====================================================================
# DASHBOARD & TELEMETRY HOOKS (Owner: @Thariq)
# =====================================================================
def update_dashboard(state_dict):
    """Writes telemetry to file for Thariq's Streamlit Dashboard."""
    with open("telemetry.json", "w") as f:
        json.dump(state_dict, f)

def check_kill_switch():
    """Reads emergency stop flag from Dashboard."""
    if os.path.exists("EMERGENCY_STOP.flag"):
        print("🚨 KILL SWITCH INITIATED FROM DASHBOARD! Aborting...")
        return True
    return False

# =====================================================================
# FLIGHT PRIMITIVES & ESTIMATION (Owner: @Muhammad)
# =====================================================================
async def do(cmd):
    """Wait for flight command to finish."""
    await (await cmd)

async def precise_move(drone, n, e, d, speed):
    """
    TODO (@Muhammad): Wrap move_to_position_async here.
    Add your estimate-vs-truth drift characterisation and logging in this wrapper
    so Nirmal can just call this cleanly without worrying about the math.
    """
    await do(drone.move_to_position_async(n, e, d, speed))

# =====================================================================
# TERMINAL MANEUVERS & RECOVERY (Owner: @Tomotaka)
# =====================================================================
async def execute_delivery(drone, vehicle_target):
    """
    TODO (@Tomotaka): Implement the terminal phase.
    If Tank/Boat/Jet -> fly into it. 
    If Ice-Cream Truck -> use land_async() within 50m.
    """
    pass

async def recover_from_stall(drone):
    """
    TODO (@Tomotaka): Implement a crash/stall recovery sequence.
    Example: If drone velocity is 0 for 5 seconds but altitude > 0, trigger reset().
    """
    pass

# =====================================================================
# MAIN DECISION LOGIC & STATE MACHINE (Owner: @Nirmal)
# =====================================================================
async def solve(drone, alt, speed):
    """
    TODO (@Nirmal): Build the main state machine loop here.
    Manage the states: JUMP_TO_ARROWS -> SCAN -> JUMP_TO_SPHERES -> DELIVER
    """
    current_state = "INITIALIZING"
    
    while True:
        # 1. DASHBOARD SAFETY OVERRIDE
        if check_kill_switch():
            await do(drone.land_async())
            break
            
        # 2. GATHER DATA
        state = drone.get_estimated_kinematics()
        pos = state.get("pose", {}).get("position", {})
        frame = read_frame(drone)
        clue = get_clue_data(frame)
        
        # 3. PUSH TELEMETRY TO DASHBOARD
        update_dashboard({
            "status": current_state,
            "altitude": -pos.get("z", 0), # NED coordinates: Z is negative up
            "last_decision": clue.get("direction", "None"),
            "spheres_seen": clue.get("sphere_count", 0)
        })
        
        # 4. EXECUTE STATE LOGIC
        # TODO (@Nirmal): Use the clue logic to route the drone using Muhammad's 
        # precise_move() primitive, and end with Tomotaka's execute_delivery().
        
        # Temporary break to prevent infinite loops before logic is written
        await asyncio.sleep(0.5) 
        break

# =====================================================================
# SYSTEM ENTRY POINT
# =====================================================================
async def fly(address: str, alt: float, speed: float):
    client, world, drone = connect(address)
    try:
        drone.enable_api_control()
        drone.arm()
        await do(drone.takeoff_async())
        
        # Hand over control to Nirmal's solve logic
        await solve(drone, alt, speed)
        
    finally:
        client.disconnect()

if __name__ == "__main__":
    # Remove any old kill switches before starting a new run
    if os.path.exists("EMERGENCY_STOP.flag"):
        os.remove("EMERGENCY_STOP.flag")
        
    asyncio.run(fly("127.0.0.1", 5.0, 3.0))