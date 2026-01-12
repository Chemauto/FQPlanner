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
    # Debug: Log to stderr so it's visible even in MCP stdio mode
    print(f"[SKILL DEBUG] navigate_to_target called with target='{target}'", file=sys.stderr)

    # In a real robot, this would contain navigation logic.
    # For simulation, we just confirm the action is "done".
    result = f"Navigation to {target} has been successfully performed."

    print(f"[SKILL DEBUG] Result: {result}", file=sys.stderr)
    print(result)  # This will go to stdout, which MCP captures

    # The returned dictionary updates the robot's state.
    print(f"[SKILL DEBUG] Returning tuple: ({result!r}, {{'position': {target!r}}})", file=sys.stderr)
    return result, {"position": f"{target}"}


if __name__ == "__main__":
    # Initialize and run the MCP server to listen for tool calls.
    mcp.run(transport="stdio")