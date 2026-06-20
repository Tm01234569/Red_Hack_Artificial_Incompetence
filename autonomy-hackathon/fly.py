#!/usr/bin/env python3
import argparse
import asyncio
from redteam_sim import connect, read_frame 

# 'do' helper from your original template
async def do(cmd):
    """Send a *_async() flight command and wait until the maneuver finishes."""
    await (await cmd)

async def fly_and_hover(address: str, alt: float):
    # Connects to the simulator and spawns the drone
    client, world, drone = connect(address)
    
    try:
        print(">> Arming")
        drone.enable_api_control()
        drone.arm()

        # Command the takeoff
        print(f">> Taking off to {alt:.0f} meters")
        await do(drone.takeoff_async())

        # Hold position: X=0, Y=0, Z=-alt
        print(f">> Hovering at {alt:.0f} meters")
        await do(drone.move_to_position_async(0.0, 0.0, -alt, 1.0))
        
        # Keep the script running to maintain the hover
        print(">> Holding position for 10 seconds...")
        await asyncio.sleep(10) 

        print(">> Landing")
        await do(drone.land_async())
        drone.disarm()
        
    finally:
        client.disconnect()

if __name__ == "__main__":
    # This now calls your custom hover function
    asyncio.run(fly_and_hover("127.0.0.1", 5.0))