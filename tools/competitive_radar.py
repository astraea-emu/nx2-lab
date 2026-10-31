#!/usr/bin/env python3
"""Public-GitHub-metadata watch. Does not run third-party code or replan NX2."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

START = "<!-- nx2-radar:start -->"
END = "<!-- nx2-radar:end -->"
TITLE = "NX2 competitive radar — automated metadata (not compatibility evidence)"
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[0-9a-f]{40}$")


class RadarError(RuntimeError):
    pass


def api(path, token, method="GET", payload=None):
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "nx2-lab-competitor-radar",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None if payload is None else json.dumps(payload).encode()
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request("https://api.github.com" + path, data=data,
                      headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read(2_000_000)
            return json.loads(raw) if raw else {}
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        # Never print request headers, response bodies or tokens.
        raise RadarError("GitHub API request failed: " + method + " " + path +
                         " (" + type(exc).__name__ + ")") from None


def watchlist(path):
    names = json.loads(Path(path).read_text(encoding="utf-8"))["repositories"]
    if not isinstance(names, list) or not 1 <= len(names) <= 20:
        raise RadarError("Need 1..20 configured repositories")
    if any(not isinstance(x, str) or not REPO.fullmatch(x) for x in names):
        raise RadarError("Invalid repository identifier")
    if len(names) != len(set(names)):
        raise RadarError("Duplicate repository")
    return names


def collect(names, token):
    state = {}
    for name in names:
        metadata = api("/repos/" + name, token)
        if metadata.get("full_name", "").lower() != name.lower():
            raise RadarError("Watchlist repository renamed: " + name)
        sha = api("/repos/" + name + "/commits?per_page=1", token)[0]["sha"]
        if not SHA.fullmatch(sha):
            raise RadarError("Bad head SHA returned: " + name)
        runs = api("/repos/" + name + "/actions/runs?per_page=1", token).get("workflow_runs", [])
        run = runs[0] if runs else None
        state[name] = {
            "sha": sha,
            "archived": bool(metadata["archived"]),
            "workflow": None if run is None else {
                "sha": run["head_sha"],
                "conclusion": run.get("conclusion") or run.get("status") or "unknown"
            }
        }
    return state


def previous(body):
    match = re.search(r"<!-- nx2-radar-state:(\{[^\n]*\}) -->", body or "")
    if not match:
        return {}
    try:
        state = json.loads(match.group(1))
        return state if isinstance(state, dict) else {}
    except ValueError:
        return {}


def render(names, state, old, timestamp):
    lines = [
        "**Metadata-only watch.** A commit, successful CI run, screenshot or author's"
        " README is not a verified Switch 2 emulator capability.",
        "",
        "Checked UTC: `" + timestamp + "`. Source: public GitHub REST API.",
        "",
        "| Repository | Head | Since last scan | Latest GitHub Actions run |",
        "| --- | --- | --- | --- |"
    ]
    for name in names:
        item = state[name]
        sha = item["sha"]
        status = ("First scan" if name not in old else
                  "Changed" if old[name].get("sha") != sha else "Unchanged")
        if item["archived"]:
            status += "; archived"
        run = item["workflow"]
        if run is None:
            ci = "No public GitHub Actions runs found"
        else:
            result = re.sub(r"[^a-zA-Z0-9_-]", "", run["conclusion"])
            ci = result + (" (exact HEAD)" if run["sha"] == sha else " (other SHA)")
        lines.append("| [{0}](https://github.com/{0}) | [`{1}`](https://github.com/{0}/commit/{2}) | {3} | {4} |".format(
            name, sha[:12], sha, status, ci))
    changed = sum(name in old and old[name].get("sha") != state[name]["sha"] for name in names)
    lines += [
        "",
        "**Changed revisions:** " + str(changed) + ". Review relevant source diffs, reproducibility and"
        " negative tests before proposing a change to the [primary gate](https://github.com/astraea-emu/nx2-lab/issues/21).",
        "",
        "**Not monitored:** Eden's external Git server, private forks, non-GitHub"
        " research, security disclosures, actual game execution or graphics correctness.",
        "",
        "<!-- nx2-radar-state:" + json.dumps(state, sort_keys=True, separators=(",", ":")) + " -->"
    ]
    return "\n".join(lines)


def replace_section(body, section):
    block = START + "\n" + section + "\n" + END
    if not body:
        return ("# NX2 competitive radar\n\n" + block + "\n\n---\n"
                "Human notes outside the marked section are preserved.\n"
                "Changes to the roadmap require [the decision protocol](https://github.com/astraea-emu/nx2-lab/blob/main/docs/PLAN.md#how-decisions-change).\n")
    if body.count(START) != 1 or body.count(END) != 1:
        raise RadarError("Refusing to overwrite an issue without unique owned markers")
    begin, finish = body.index(START), body.index(END)
    if finish < begin:
        raise RadarError("Misordered issue markers")
    return body[:begin] + block + body[finish + len(END):]


def find_issue(repo, token):
    # Do not open a new issue when an earlier radar issue has been closed.
    matches = []
    for page in (1, 2):
        issues = api("/repos/" + repo + "/issues?state=all&per_page=100&page=" + str(page), token)
        matches += [i for i in issues if i.get("title") == TITLE and "pull_request" not in i]
        if len(issues) < 100:
            break
    if len(matches) > 1:
        raise RadarError("Duplicate radar issues found; review manually")
    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="tools/competitive_radar.json")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    names = watchlist(args.config)
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if args.publish and (not token or not REPO.fullmatch(repo)):
        raise RadarError("Publishing requires GITHUB_TOKEN and GITHUB_REPOSITORY")
    issue = find_issue(repo, token) if args.publish else None
    old = previous(issue.get("body") or "") if issue else {}
    current = collect(names, token)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    text = render(names, current, old, now)
    if not args.publish:
        print(text)
        return
    body = replace_section(issue.get("body") or "", text) if issue else replace_section("", text)
    if issue:
        if issue.get("state") != "open":
            raise RadarError("Radar issue closed; reopen it manually")
        if body != issue.get("body"):
            api("/repos/" + repo + "/issues/" + str(issue["number"]), token, "PATCH", {"body": body})
        print("Updated: " + issue["html_url"])
    else:
        created = api("/repos/" + repo + "/issues", token, "POST", {"title": TITLE, "body": body})
        print("Created: " + created["html_url"])


if __name__ == "__main__":
    try:
        main()
    except (RadarError, KeyError, IndexError, ValueError, TypeError) as err:
        print("RADAR_FAILED: " + str(err), file=sys.stderr)
        sys.exit(1)
