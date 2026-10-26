import argparse
import json
import sys

from . import core


def main():
    p = argparse.ArgumentParser(prog="ytmcp")
    p.add_argument("cmd", choices=["auth", "serve", "test"])
    cmd = p.parse_args().cmd
    if cmd == "serve":
        from .server import mcp
        mcp.run(transport="stdio")
        return
    try:
        if cmd == "auth":
            core.run_auth()
            ch = core.get_channel()
            print(f"Signed in. Channel: {ch['title']} ({ch['channelId']}).")
        else:
            print(json.dumps(core.sync_snapshot(), indent=2, ensure_ascii=False))
    except core.ToolFailure as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
