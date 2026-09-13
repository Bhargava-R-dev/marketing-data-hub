import sys

from hub.cli import app

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "setup"]  # windowed: always the home page
    app()
