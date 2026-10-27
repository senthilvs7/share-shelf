# share-shelf

A shelf for temporary HTML artifacts that I share by link. Each artifact is one file with a link that cannot be guessed. To take an artifact down, I move it out of the published folder.

Warning: this repo is public, because GitHub Pages on the Free plan needs a public repo. Anyone who finds the repo can see the file list and the history. Put no work data, tokens, or personal data in an artifact.

## Layout

| Path | What it holds |
|---|---|
| `site/` | Live artifacts. Only this folder goes online. |
| `site/<code>/<name>.html` | One artifact. `<code>` is a random 12-character string. |
| `retired/` | Artifacts taken down. Not published. They stay in the repo history. |
| `scripts/shelf.py` | The tool that adds, retires, and lists artifacts. It uses only the Python standard library. |
| `.github/workflows/pages.yml` | Builds the site and deploys it on each push to `main`. |

## Daily use

Add an artifact:

```bash
python3 scripts/shelf.py add ~/Downloads/report.html --name q3-plan
```

The command copies the file to `site/<code>/q3-plan.html`, adds a `noindex` tag, and prints the link. Commit and push so the workflow deploys it.

Take an artifact down:

```bash
python3 scripts/shelf.py retire q3-plan
```

The command moves the file to `retired/`, commits, and pushes. The link returns 404 after the deploy and the cache delay, about 10 minutes. Add `--no-push` to skip the push. If the query matches more than one file, the command lists them and stops.

## The index

My index is a local page, `.local/index.html`. I make it with `python3 scripts/shelf.py index`. It shows the number of live artifacts, a search box, the date added, and a copy-link button for each artifact. It is built from the files in `site/`, so nothing needs a hand edit. It is never committed or deployed. The root page of the live site is blank.

### Optional: a live index (off)

The deploy can also publish the same index at a secret path. This is off unless the repo secret `INDEX_PATH` is set. Do not turn it on for private use:

- The page is public. Anyone who has its link can open it.
- The workflow uploads the built site as an Actions artifact, and in a public repo any signed-in GitHub user can download it. The artifact holds the secret path. The workflow keeps it for 1 day.

To turn it on: run `python3 scripts/shelf.py token`, then save the value as the repo secret `INDEX_PATH` in **Settings** > **Secrets and variables** > **Actions**. The live index is at `https://senthilvs7.github.io/share-shelf/<value>/`.

## How a change goes online

1. You push to `main`.
2. The workflow runs `shelf.py build`, which copies `site/` to `_site/`. It adds the live index only if `INDEX_PATH` is set.
3. The workflow publishes `_site/` with GitHub Pages.
4. The site is at `https://senthilvs7.github.io/share-shelf/`. The root page is blank.
