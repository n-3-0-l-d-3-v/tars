"""__TARS_PROJECT_NAME__ CLI."""

from __future__ import annotations

import argparse


def greet(name: str) -> str:
    return f"Hello, {name}! This is __TARS_PROJECT_NAME__."


def main() -> None:
    parser = argparse.ArgumentParser(prog="__TARS_PROJECT_NAME__")
    parser.add_argument("--name", default="World", help="Who to greet.")
    args = parser.parse_args()
    print(greet(args.name))


if __name__ == "__main__":
    main()
