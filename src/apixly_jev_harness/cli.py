from .task_cli import main


def entrypoint():
    raise SystemExit(main())
