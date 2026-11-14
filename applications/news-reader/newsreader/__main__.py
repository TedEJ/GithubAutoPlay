"""python -m newsreader --out build [--previous <file>]  (R12.1)"""
import argparse
import sys
from datetime import datetime, timezone

from . import fetch as fetch_module
from .build import BuildError, build

DESCRIPTION = ("Fetch the approved build sources, sort their items into topics and write "
               "news.json (version 2) and the page files into the output folder.")


def main(argv=None, fetch=None, now=None, root=None):
    """Run the command. `fetch`, `now` and `root` are for tests; the defaults are
    the real fetch layer, the clock and the project folder. Returns the exit code."""
    parser = argparse.ArgumentParser(prog="python -m newsreader", description=DESCRIPTION)
    parser.add_argument("--out", required=True, help="output folder, for example build")
    parser.add_argument("--previous", default=None,
                        help="previous news.json for the 24-hour fallback (default: <out>/news.json if it exists)")
    parser.add_argument("--ca-file", default=None, metavar="PATH",
                        help="PEM or DER file with an extra certificate (for example a missing intermediate "
                             "certificate) to trust in addition to the system store, for every host the build "
                             "fetches; verification stays on")
    args = parser.parse_args(argv)
    context = None
    if args.ca_file is not None:  # checked before anything is fetched or written
        try:
            context = fetch_module.make_ssl_context(args.ca_file)
        except fetch_module.CaFileError as exc:
            parser.error("--ca-file: %s" % exc)  # exit code 2, like any argument error
    if fetch is None:
        fetch = fetch_module.fetch_url if context is None else fetch_module.make_fetch(context)
    kwargs = {} if root is None else {"root": root}
    try:
        document = build(
            args.out,
            now if now is not None else datetime.now(timezone.utc),
            fetch,
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
        for feed in source["feeds"]:  # the status of each feed (R19.3)
            line = "  %s: %s, %d items" % (feed["topic"], feed["status"], feed["itemCount"])
            if feed.get("message"):
                line += " (%s)" % feed["message"]
            print(line)
    print("wrote %s" % (args.out.rstrip("/\\") + "/news.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
