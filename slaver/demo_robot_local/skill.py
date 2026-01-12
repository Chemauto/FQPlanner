import sys
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("robots")


@mcp.tool()
async def navigate_to_target(target: str) -> tuple[str, dict]:
    """Navigate to a target location.

    Args:
        target: The name of the navigation destination (e.g., "kitchenTable", "trashCan").
    """
    # In a real robot, this would contain navigation logic.
    # For simulation, we just confirm the action is "done".
    result = f"Navigation to {target} has been successfully performed."

    # Log to stderr for debugging (visible in terminal)
    print(f"[navigate_to_target] Called with target='{target}', result: {result}", file=sys.stderr)

    # The returned dictionary updates the robot's state.
    return result, {"position": f"{target}"}


@mcp.tool()
async def move(direction: float, speed: float, duration: float) -> tuple[str, dict]:
    """Move the robot in a specific direction with given speed and duration.

    Args:
        direction: Movement direction in robot coordinate system (0-360 degrees).
                   0 degrees = forward (positive direction of robot's coordinate system),
                   90 degrees = left, 180 degrees = backward, 270 degrees = right.
        speed: Movement speed in meters per second (e.g., 0.5 m/s).
        duration: Movement duration in seconds (e.g., 2.0 seconds).

    Returns:
        A tuple containing the result message and updated robot state.

    Example:
        move(direction=0.0, speed=1.0, duration=2.0)  # Move forward at 1 m/s for 2 seconds
        move(direction=90.0, speed=0.5, duration=3.0)  # Move left at 0.5 m/s for 3 seconds
    """
    # Calculate the distance moved
    distance = speed * duration

    # Normalize direction to 0-360 range
    direction_normalized = direction % 360

    # Determine direction description for better logging
    if direction_normalized == 0:
        direction_desc = "forward"
    elif direction_normalized == 90:
        direction_desc = "left"
    elif direction_normalized == 180:
        direction_desc = "backward"
    elif direction_normalized == 270:
        direction_desc = "right"
    else:
        direction_desc = f"{direction_normalized}°"

    # In a real robot, this would send commands to the motor controller.
    # For simulation, we just confirm the action is "done".
    result = f"Successfully moved {direction_desc} at {speed} m/s for {duration} seconds (distance: {distance:.2f} m)."

    # Log to stderr for debugging (visible in terminal)
    print(f"[move] Called with direction={direction}°, speed={speed} m/s, duration={duration} s, result: {result}", file=sys.stderr)

    # The returned dictionary updates the robot's state.
    # We record the movement parameters for potential future use.
    return result, {
        "last_movement": {
            "direction": direction_normalized,
            "speed": speed,
            "duration": duration,
            "distance": distance
        }
    }


if __name__ == "__main__":
    # Initialize and run the MCP server to listen for tool calls.
    mcp.run(transport="stdio")