import inspect
import json
from pathlib import Path

from sonar_mcp.__main__ import server

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "tool_schemas.json"


def _normalise(tool_dict: dict) -> dict:  # type: ignore[type-arg]
    # FastMCP strips docstring indentation on some platforms but not others;
    # normalise here so the snapshot is platform-independent.
    if tool_dict.get("description"):
        tool_dict["description"] = inspect.cleandoc(tool_dict["description"])
    return tool_dict


def _serialise(tools: list) -> str:  # type: ignore[type-arg]
    return json.dumps(
        sorted([_normalise(t.model_dump()) for t in tools], key=lambda t: t["name"]),
        sort_keys=True,
        indent=2,
    )


async def test_tool_schemas_match_snapshot() -> None:
    tools = await server.list_tools()
    actual = _serialise(tools)

    if not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.write_text(actual, encoding="utf-8")
        raise AssertionError(
            f"Snapshot did not exist — created {SNAPSHOT_PATH}. Commit it and re-run the tests."
        )

    expected = SNAPSHOT_PATH.read_text(encoding="utf-8")
    if actual != expected:
        import difflib

        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile="tests/snapshots/tool_schemas.json (committed)",
                tofile="server.list_tools() (current)",
                lineterm="",
            )
        )
        raise AssertionError(
            "Tool schemas have changed. Update tests/snapshots/tool_schemas.json "
            "if the change is intentional.\n\n" + diff
        )
