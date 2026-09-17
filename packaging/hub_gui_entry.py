import sys

from hub.cli import app

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("setup")
    app()
