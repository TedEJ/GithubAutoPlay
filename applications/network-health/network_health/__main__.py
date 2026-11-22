import sys

from .cli import main

# Names of networks and programs can contain any character; never crash on
# printing them to a console or file with a limited code page.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

sys.exit(main())
