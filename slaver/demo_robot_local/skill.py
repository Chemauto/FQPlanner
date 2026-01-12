from mcp.server.fastmcp import FastMCP
import math

# Initialize FastMCP server
mcp = FastMCP("robots")


@mcp.tool()
async def navigate_to_target(target: str) -> tuple[str, dict]:
    """
    Navigate to a predefined target location. This is for moving to known landmarks.
    Args:
        target: The name of the navigation destination (eg., "kitchenTable", "trashCan").
    """
    # In a real robot, this would contain navigation logic.
    # For simulation, we just confirm the action is "done".
    result = f"Navigation to {target} has been successfully performed."
    print(result)
    # The returned dictionary updates the robot's state.
    return result, {"position": f"{target}"}


@mcp.tool()
async def move(direction: float, speed: float, duration: float) -> tuple[str, dict]:
    """
    Move the robot in a specific direction for a certain duration. This is for precise, relative movements.
    Args:
        direction: The direction of movement in degrees (0-360), where 0 is forward.
        speed: The speed of movement in meters per second.
        duration: The duration of the movement in seconds.
    """
    # In a real robot, this would contain motor control logic.
    # For simulation, we calculate the traveled distance and confirm the action.
    distance = speed * duration
    result = f"Moved {distance:.2f} meters at a {direction} degree angle."
    print(result)
    
    # In a real scenario, you might want to update the robot's internal coordinates here.
    # For now, we just return a success status.
    return result, {"status": "completed", "moved_distance": f"{distance:.2f}m"}


if __name__ == "__main__":
    # Initialize and run the MCP server to listen for tool calls.
    mcp.run(transport="stdio")
