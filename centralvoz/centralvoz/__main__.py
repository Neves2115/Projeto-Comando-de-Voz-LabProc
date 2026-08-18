"""Permite `python -m centralvoz ...` alem do comando `voz`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
