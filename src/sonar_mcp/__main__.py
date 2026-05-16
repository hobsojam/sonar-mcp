import os
import sys

from mcp.server.fastmcp import FastMCP

from sonar_mcp.tools.issues import get_issue_summary, get_issues
from sonar_mcp.tools.quality_gate import get_quality_gate

server = FastMCP("sonar-mcp")
server.tool()(get_quality_gate)
server.tool()(get_issues)
server.tool()(get_issue_summary)


def main() -> None:
    if not os.environ.get("SONAR_TOKEN"):
        sys.exit("Error: SONAR_TOKEN environment variable is required.")
    server.run()


if __name__ == "__main__":
    main()
