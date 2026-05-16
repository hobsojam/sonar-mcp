import os
import sys

from mcp.server.fastmcp import FastMCP

server = FastMCP("sonar-mcp")


def main() -> None:
    if not os.environ.get("SONAR_TOKEN"):
        sys.exit("Error: SONAR_TOKEN environment variable is required.")
    server.run()


if __name__ == "__main__":
    main()
