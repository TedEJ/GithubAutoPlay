"""python -m newsreader --out build [--previous <file>]  (R12.1)"""
import argparse
import sys
from datetime import datetime, timezone

from . import fetch as fetch_module
from .build import BuildError, build

DESCRIPTION = ("Fetch the approved build sources, select the politics items and write "
               "news.json and the page files into the output folder.")


def main(argv=None, fetch=None, now=None, root=None):
    """Run the command. `fetch`, `now` and `root` are for tests; the defaults are
    the real fetch layer, the clock and the project folder. Returns the exit code."""
    parser = argparse.ArgumentParser(prog="python -m newsreader", description=DESCRIPTION)
    parser.add_argument("--out", required=True, help="output folder, for example build")
    parser.add_argument("--previous", default=None,
                        help="previous news.json for the 24-hour fallback (default: <out>/news.json if it exists)")
    args = parser.parse_args(argv)
    kwargs = {} if root is None else {"root": root}
    try:
        document = build(
            args.out,
            now if now is not None else datetime.now(timezone.utc),
            fetch if fetch is not None else fetch_module.fetch_url,
            previous_path=args.previous,
            **kwargs,
        )
    except BuildError as exc:
        print("newsreader: build failed: %s" % exc, file=sys.stderr)
        return 1
    for source in document["sources"]:
        line = "%s: %s, %d items" % (source["id"], source["status"], source["itemCount"])
        if source.get("message"):
            line += " (%s)" % source["message"]
        print(line)
    print("wrote %s" % (args.out.rstrip("/\\") + "/news.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
