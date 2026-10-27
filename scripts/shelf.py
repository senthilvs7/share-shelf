#!/usr/bin/env python3
"""share-shelf: add, retire, and list shared HTML artifacts.

Commands:
  add FILE [--name SLUG]   copy an HTML file into site/<random>/ and print its link
  retire QUERY [--no-push] move one artifact to retired/, commit, and push
  index                    write a private index to .local/index.html
  build --out DIR          copy site/ to DIR and add the index at $INDEX_PATH (used by the workflow)
  token                    print a random value for the INDEX_PATH secret
"""

import argparse
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
RETIRED = ROOT / "retired"
LOCAL = ROOT / ".local"
NOINDEX = '<meta name="robots" content="noindex">'
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{8,}")


def git(*args, check=True):
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=check, capture_output=True, text=True
    )
    return result.stdout.strip()


def base_url():
    url = git("remote", "get-url", "origin", check=False)
    match = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?$", url)
    return f"https://{match[1].lower()}.github.io/{match[2]}/" if match else ""


def added_dates():
    """Map each path under site/ to the date it was first committed."""
    out = git("-c", "core.quotepath=false", "log", "--diff-filter=A", "--name-only",
              "--format=%x00%aI", "--", "site", check=False)
    dates, current = {}, ""
    for line in out.splitlines():
        if line.startswith("\x00"):
            current = line[1:11]
        elif line:
            dates[line] = current
    return dates


def file_date(path, dates):
    rel = path.relative_to(ROOT).as_posix()
    if rel in dates:
        return dates[rel]
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).strftime("%Y-%m-%d")


def artifacts():
    """Return one row per HTML file in a subfolder of site/, newest first."""
    rows = []
    dates = added_dates()
    for path in sorted(SITE.rglob("*.html")):
        rel = path.relative_to(SITE).as_posix()
        if "/" not in rel:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        title = html.unescape(" ".join(match[1].split())) if match else ""
        rows.append({"title": title or path.stem, "path": rel, "date": file_date(path, dates)})
    rows.sort(key=lambda row: (row["date"], row["path"]), reverse=True)
    return rows


INDEX_TEMPLATE = (Path(__file__).resolve().parent / "index.template.html").read_text(encoding="utf-8")


def render_index(rows, prefix):
    def js(value):
        return json.dumps(value).replace("<", "\\u003c")

    values = {"ROWS": js(rows), "PREFIX": js(prefix), "BASE": js(base_url())}
    # One pass, so text inside a value is never read as a placeholder.
    return re.sub(r"__(ROWS|PREFIX|BASE)__", lambda m: values[m[1]], INDEX_TEMPLATE)


def add_noindex(text):
    """Add a noindex tag unless an active robots tag already has one."""
    if re.search(
        r"<meta[^>]*(robots[^>]*noindex|noindex[^>]*robots)",
        re.sub(r"<!--.*?-->", "", text, flags=re.S),
        re.I,
    ):
        return text
    # Insert after <head>; else wrap in a <head> after <html>; else after the doctype.
    for pattern, wrap in (
        (r"<head(?:\s[^>]*)?>", False),
        (r"<html(?:\s[^>]*)?>", True),
        (r"<!doctype[^>]*>", False),
    ):
        match = re.search(pattern, text, re.I)
        if match:
            tag = f"<head>{NOINDEX}</head>" if wrap else NOINDEX
            return text[: match.end()] + "\n" + tag + text[match.end() :]
    return NOINDEX + "\n" + text


def cmd_add(args):
    src = Path(args.file).expanduser()
    if not src.is_file() or src.suffix.lower() != ".html":
        sys.exit("Give the path of an .html file.")
    name = args.name or src.stem
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "page"
    dest = SITE / secrets.token_hex(6) / f"{slug}.html"
    try:
        text = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        sys.exit("The file is not UTF-8 text. Save it as UTF-8 and try again.")
    dest.parent.mkdir(parents=True)
    dest.write_text(add_noindex(text), encoding="utf-8")
    rel = dest.relative_to(SITE).as_posix()
    print(f"Added site/{rel}")
    print(f"Link after deploy: {base_url()}{rel}")
    print("Next: commit and push so the workflow deploys it.")


def cmd_retire(args):
    hits = [
        p
        for p in SITE.rglob("*.html")
        if "/" in p.relative_to(SITE).as_posix()
        and args.query in p.relative_to(SITE).as_posix()
    ]
    if len(hits) != 1:
        names = "\n".join(f"  {p.relative_to(SITE).as_posix()}" for p in hits)
        sys.exit(f"Expected 1 match for '{args.query}', found {len(hits)}.\n{names}")
    src = hits[0]
    rel = src.relative_to(SITE)
    dest = RETIRED / rel
    src_rel = src.relative_to(ROOT).as_posix()
    dest_rel = dest.relative_to(ROOT).as_posix()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if git("ls-files", "--", src_rel):
        git("mv", src_rel, dest_rel)
        paths = [src_rel, dest_rel]
    else:
        shutil.move(str(src), str(dest))
        git("add", "--", dest_rel)
        paths = [dest_rel]
    try:
        src.parent.rmdir()
    except OSError:
        pass
    # Commit only these paths, so other pending or staged work stays out.
    git("commit", "-m", f"[retire] {rel.as_posix()}", "--", *paths)
    print(f"Moved to retired/{rel.as_posix()} and committed.")
    if args.no_push:
        print("Not pushed. Run: git push")
    else:
        git("push")
        print("Pushed. The link returns 404 after the deploy and cache delay (about 10 minutes).")


def cmd_index(_args):
    rows = artifacts()
    LOCAL.mkdir(exist_ok=True)
    out = LOCAL / "index.html"
    out.write_text(render_index(rows, "../site/"), encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({len(rows)} artifacts). Open it in a browser.")


def check_build_dir(out):
    """The build deletes its output folder, so allow only _site* directly in the repo."""
    if out.parent != ROOT or not out.name.startswith("_site"):
        sys.exit(f"Refusing to build into {out}. Use a folder such as _site inside the repo.")


def cmd_build(args):
    out = Path(args.out).resolve()
    check_build_dir(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE, out)
    token = os.environ.get("INDEX_PATH", "").strip()
    if not token:
        print("INDEX_PATH is not set: no index is published.")
        return
    if not TOKEN_RE.fullmatch(token):
        sys.exit("INDEX_PATH must have 8 or more letters, digits, - or _.")
    rows = artifacts()
    (out / token).mkdir()
    (out / token / "index.html").write_text(render_index(rows, "../"), encoding="utf-8")
    print(f"Built site with a private index of {len(rows)} artifacts.")


def cmd_token(_args):
    print(secrets.token_hex(8))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="add an HTML file")
    add.add_argument("file")
    add.add_argument("--name")
    add.set_defaults(func=cmd_add)
    retire = sub.add_parser("retire", help="move an artifact to retired/")
    retire.add_argument("query", help="part of the artifact path, for example its folder code")
    retire.add_argument("--no-push", action="store_true")
    retire.set_defaults(func=cmd_retire)
    sub.add_parser("index", help="write a local index").set_defaults(func=cmd_index)
    build = sub.add_parser("build", help="build the site folder for deploy")
    build.add_argument("--out", required=True)
    build.set_defaults(func=cmd_build)
    sub.add_parser("token", help="print a random index path").set_defaults(func=cmd_token)
    args = parser.parse_args()
    try:
        args.func(args)
    except subprocess.CalledProcessError as err:
        sys.exit(f"git failed: {err.stderr.strip() or err}")


if __name__ == "__main__":
    main()
