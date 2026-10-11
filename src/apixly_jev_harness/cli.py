"""Public task CLI, with optional stdio MCP exposure of the same trusted script."""

import sys


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "mcp":
        from .mcp import main as mcp_main

        return mcp_main(args[1:])
    from .task_cli import main as task_main

    return task_main(args)


def entrypoint():
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
