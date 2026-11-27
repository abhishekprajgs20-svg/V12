#!/usr/bin/env python3
# TXT 2 SHORTS V12 — GitHub uploader based on the user's working QUIZINOX uploader.
# Git for Windows is NOT required. All repository operations use GitHub REST API.
# Requires Python 3.9+ and requests (the companion BAT installs requests if missing).
# The PAT is requested with hidden input and is never written to disk.

import base64
import getpass
import io
import json
import os
import re
import sys
import time
import traceback
import zipfile
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("Missing Python package 'requests'. The RUN_GITHUB_BUILDER.bat should install it automatically.")
    print("If needed, run: py -3 -m pip install --user requests")
    input("Press Enter to exit...")
    sys.exit(1)

API = "https://api.github.com"
HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = 1_500_000
SKIP_DIRS = {
    ".git", "__pycache__", ".buildozer", ".ffmpeg-build", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".venv", "venv", "github_apk_download",
}
SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini", "upload_log.txt"}
SKIP_EXT = {".apk", ".aab", ".exe", ".pyc", ".pyo", ".log", ".tmp"}
TARGETS = {
    "android": {
        "workflow": "android-apk.yml",
        "artifact": "txt2shorts-v12-universal-apk",
        "label": "TXT 2 SHORTS V12 Universal Android APK",
        "filename": "TXT2SHORTS_V12_Universal.apk",
        "extension": ".apk",
    }
}

class UploadError(Exception):
    pass


def find_project_dir():
    candidates = [
        HERE,
        os.path.join(HERE, "txt2shorts_android"),
        os.path.join(os.path.dirname(HERE), "txt2shorts_android"),
    ]
    required = [
        "buildozer.spec", "main.py", "engine_v12.py",
        os.path.join(".github", "workflows", "android-apk.yml"),
        os.path.join("scripts", "build_ffmpeg_android.sh"),
    ]
    for candidate in candidates:
        if all(os.path.isfile(os.path.join(candidate, item)) for item in required):
            return os.path.abspath(candidate)
    return None


PROJECT_DIR = find_project_dir()


def app_version():
    try:
        with open(os.path.join(PROJECT_DIR, "buildozer.spec"), encoding="utf-8") as f:
            content = f.read()
        match = re.search(r"(?m)^\s*version\s*=\s*([^\s#]+)", content)
        return match.group(1).strip() if match else "12.0.0"
    except Exception:
        return "12.0.0"


def api(method, path, token, **kwargs):
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "TXT2SHORTS-V12-GitHub-Uploader/4.0",
    }
    url = path if path.startswith("https://") else API + path
    for attempt in range(1, 8):
        try:
            response = requests.request(method, url, headers=headers, timeout=120, **kwargs)
        except requests.RequestException as exc:
            print(f"  Network issue ({type(exc).__name__}), retry {attempt}/7...", flush=True)
            time.sleep(attempt * 3)
            continue
        if response.status_code == 429 or (
            response.status_code == 403 and any(x in response.text.lower() for x in ("rate limit", "abuse", "secondary"))
        ):
            wait = int(response.headers.get("Retry-After", 0) or 20 * attempt)
            print(f"  GitHub rate limit; waiting {wait}s...", flush=True)
            time.sleep(wait)
            continue
        if response.status_code >= 500:
            print(f"  GitHub server error {response.status_code}; retrying...", flush=True)
            time.sleep(attempt * 4)
            continue
        return response
    raise UploadError(f"GitHub API failed repeatedly: {method} {path}")


def collect():
    if not PROJECT_DIR:
        raise UploadError(
            "TXT 2 SHORTS project files were not found. Run this uploader from the extracted "
            "txt2shorts_android folder. It must contain buildozer.spec, main.py, engine_v12.py, "
            ".github/workflows/android-apk.yml and scripts/build_ffmpeg_android.sh."
        )
    print("Project folder:", PROJECT_DIR, flush=True)
    out = []
    total = 0
    for dp, dn, fn in os.walk(PROJECT_DIR):
        rel_dir = os.path.relpath(dp, PROJECT_DIR)
        # Skip generated root build output only; keep assets/bin if a user supplies ABI binaries.
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not (rel_dir == "." and d == "bin")]
        for name in fn:
            if name in SKIP_FILES or os.path.splitext(name)[1].lower() in SKIP_EXT:
                continue
            full = os.path.join(dp, name)
            rel = os.path.relpath(full, PROJECT_DIR).replace(os.sep, "/")
            if rel.lower().endswith(("/txt2shorts_v12_universal.apk", "/txt2shorts_v12_apk_artifact.zip")):
                continue
            size = os.path.getsize(full)
            if size > 100 * 1024 * 1024:
                raise UploadError(f"File is larger than GitHub's 100 MB per-file limit: {rel}")
            total += size
            out.append((rel, full))
    out.sort(key=lambda item: item[0].lower())
    if not out:
        raise UploadError("No project files found to upload.")
    print(f"Found {len(out)} project files ({total / 1024 / 1024:.2f} MB).", flush=True)
    return out


def entries_for(token, repo, files):
    out = []
    for index, (rel, full) in enumerate(files, 1):
        with open(full, "rb") as f:
            data = f.read()
        mode = "100755" if rel.endswith((".sh", "gradlew")) else "100644"
        try:
            txt = data.decode("utf-8")
            if "\x00" in txt:
                raise UnicodeDecodeError("utf8", b"", 0, 1, "binary")
            out.append(({"path": rel, "mode": mode, "type": "blob", "content": txt}, len(data)))
        except UnicodeDecodeError:
            response = api(
                "POST", repo + "/git/blobs", token,
                json={"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"},
            )
            if response.status_code != 201:
                raise UploadError(f"Binary upload failed for {rel}: HTTP {response.status_code} {response.text[:500]}")
            out.append(({"path": rel, "mode": mode, "type": "blob", "sha": response.json()["sha"]}, len(data)))
        print(f"  Prepared [{index}/{len(files)}]: {rel}", flush=True)
    return out


def commit(token, repo, branch, parent, base_tree, entries, message):
    batches, current, size = [], [], 0
    for item, item_size in entries:
        if current and size + item_size > BATCH:
            batches.append(current)
            current, size = [], 0
        current.append(item)
        size += item_size
    if current:
        batches.append(current)

    tree = base_tree
    for index, batch in enumerate(batches, 1):
        payload = {"tree": batch}
        if tree:
            payload["base_tree"] = tree
        response = api("POST", repo + "/git/trees", token, json=payload)
        if response.status_code != 201:
            raise UploadError(f"Git tree batch {index} failed: HTTP {response.status_code} {response.text[:700]}")
        tree = response.json()["sha"]
        print(f"  Uploaded Git tree batch {index}/{len(batches)}", flush=True)

    commit_payload = {"message": message, "tree": tree}
    if parent:
        commit_payload["parents"] = [parent]
    response = api("POST", repo + "/git/commits", token, json=commit_payload)
    if response.status_code != 201:
        raise UploadError(f"Commit failed: HTTP {response.status_code} {response.text[:700]}")
    sha = response.json()["sha"]
    branch_ref = quote(branch, safe="")
    if parent:
        response = api("PATCH", repo + "/git/refs/heads/" + branch_ref, token,
                       json={"sha": sha, "force": False})
        if response.status_code != 200:
            raise UploadError(f"Branch update failed: HTTP {response.status_code} {response.text[:700]}")
    else:
        response = api("POST", repo + "/git/refs", token,
                       json={"ref": "refs/heads/" + branch, "sha": sha})
        if response.status_code != 201:
            raise UploadError(f"Could not create the first branch: HTTP {response.status_code} {response.text[:700]}")
    return sha


def find_run(token, repo, workflow, sha):
    response = api("GET", f"{repo}/actions/workflows/{workflow}/runs?head_sha={sha}&per_page=10", token)
    if response.status_code == 200:
        runs = response.json().get("workflow_runs", [])
        if runs:
            return runs[0]
    return None


def dispatch(token, repo, workflow, branch):
    response = api("POST", f"{repo}/actions/workflows/{workflow}/dispatches", token,
                   json={"ref": branch})
    return response.status_code == 204


def download_artifact(token, repo, run_id):
    info = TARGETS["android"]
    response = api("GET", f"{repo}/actions/runs/{run_id}/artifacts", token)
    if response.status_code != 200:
        print(f"  Could not list build artifacts: HTTP {response.status_code} {response.text[:300]}", flush=True)
        return None
    artifacts = response.json().get("artifacts", [])
    artifact = next((a for a in artifacts if a.get("name") == info["artifact"] and not a.get("expired")), None)
    if not artifact:
        print(f"  Build completed but artifact '{info['artifact']}' was not found.", flush=True)
        return None
    print("  Downloading APK artifact from GitHub...", flush=True)
    response = requests.get(
        artifact["archive_download_url"],
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "User-Agent": "TXT2SHORTS-V12-GitHub-Uploader/4.0"},
        timeout=600,
    )
    if response.status_code != 200:
        print(f"  Artifact download failed: HTTP {response.status_code}. Download it from Actions manually.", flush=True)
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(info["extension"])]
            if not names:
                print("  Artifact ZIP does not contain an APK file.", flush=True)
                return None
            apk_data = archive.read(names[0])
    except zipfile.BadZipFile:
        print("  GitHub returned an invalid artifact ZIP.", flush=True)
        return None
    destination = os.path.join(HERE, info["filename"])
    with open(destination, "wb") as f:
        f.write(apk_data)
    return destination


def wait_and_download(token, repo, sha, branch, actions_url):
    workflow = TARGETS["android"]["workflow"]
    label = TARGETS["android"]["label"]
    print("\nWaiting for GitHub Actions to build the uploaded commit...", flush=True)
    print("Android build may take 30–120+ minutes because FFmpeg is compiled for both ARM ABIs.", flush=True)
    started = time.time()
    first_run_deadline = started + 180
    dispatched = False
    run = None
    while time.time() - started < 6 * 60 * 60:
        run = find_run(token, repo, workflow, sha)
        if run:
            break
        if not dispatched and time.time() > first_run_deadline:
            print("No push-triggered run found yet; trying workflow_dispatch...", flush=True)
            if dispatch(token, repo, workflow, branch):
                print("Manual workflow dispatch accepted.", flush=True)
            else:
                print("Workflow dispatch was not accepted; continuing to check for the push run.", flush=True)
            dispatched = True
        print("  Waiting for this commit's workflow run...", flush=True)
        time.sleep(15)
    if not run:
        raise UploadError(
            "Upload finished, but GitHub Actions did not start. Open " + actions_url +
            " and check that Actions are enabled and the workflow exists on the default branch."
        )

    run_id = run["id"]
    run_url = run.get("html_url", actions_url)
    print(f"{label}: run {run_id}", flush=True)
    print("Build details:", run_url, flush=True)
    deadline = time.time() + 6 * 60 * 60
    while time.time() < deadline:
        response = api("GET", f"{repo}/actions/runs/{run_id}", token)
        if response.status_code == 200:
            current = response.json()
            status = current.get("status")
            conclusion = current.get("conclusion")
            print("  Build status: " + str(status) + (" / " + str(conclusion) if conclusion else ""), flush=True)
            if status == "completed":
                if conclusion != "success":
                    raise UploadError(f"GitHub Actions build failed ({conclusion}). Open build log: {run_url}")
                apk = download_artifact(token, repo, run_id)
                if not apk:
                    raise UploadError("Build succeeded, but APK artifact could not be downloaded. Open: " + run_url)
                return apk
        else:
            print(f"  Could not read build status: HTTP {response.status_code}", flush=True)
        time.sleep(30)
    raise UploadError("Timed out waiting for the Android build. Check GitHub Actions: " + run_url)


def main():
    print("=" * 68)
    print(" TXT 2 SHORTS V12 — GITHUB UPLOADER + UNIVERSAL APK DOWNLOADER")
    print(" Git for Windows is NOT needed; upload is done through GitHub API.")
    print("=" * 68)

    files = collect()
    version = app_version()
    print(f"\nTXT 2 SHORTS V{version} · {len(files)} files", flush=True)

    repo_name = input("\nGitHub repository name [TXT2SHORTS-V12-Android]: ").strip() or "TXT2SHORTS-V12-Android"
    username = input("GitHub username: ").strip()
    token = getpass.getpass("GitHub Personal Access Token (hidden; classic PAT needs repo + workflow): ").strip()
    if not all((repo_name, username, token)):
        raise UploadError("Repository name, GitHub username and PAT are required.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repo_name):
        raise UploadError("Invalid repository name. Use letters, numbers, dot, underscore or hyphen only.")

    response = api("GET", "/user", token)
    if response.status_code != 200:
        detail = response.text[:500]
        if response.status_code == 401:
            detail += "\nHint: PAT is invalid/expired. Create a CLASSIC token and enable repo + workflow scopes."
        elif response.status_code == 403:
            detail += "\nHint: token/account policy may not allow this action. For a classic PAT, enable repo + workflow scopes."
        raise UploadError(f"Token check failed: HTTP {response.status_code} {detail}")
    actual_username = response.json().get("login", "")
    if not actual_username:
        raise UploadError("GitHub did not return the account username for this token.")
    if actual_username.lower() != username.lower():
        print(f"Note: this token belongs to @{actual_username}; using that account.", flush=True)
    username = actual_username

    scopes = response.headers.get("X-OAuth-Scopes", "")
    if scopes:
        scope_set = {s.strip() for s in scopes.split(",")}
        if "repo" not in scope_set:
            print("WARNING: token response does not show the classic 'repo' scope.", flush=True)
        if "workflow" not in scope_set:
            print("WARNING: token response does not show the classic 'workflow' scope.", flush=True)

    repo = f"/repos/{username}/{repo_name}"
    response = api("GET", repo, token)
    if response.status_code == 404:
        visibility = input("Create repository as private? (Y/n) [Y]: ").strip().lower()
        private = visibility not in ("n", "no")
        response = api("POST", "/user/repos", token, json={
            "name": repo_name,
            "description": "TXT 2 SHORTS V12 — Universal Android video generator",
            "private": private,
            "auto_init": True,
        })
        if response.status_code != 201:
            raise UploadError(f"Could not create repository: HTTP {response.status_code} {response.text[:700]}")
        repo_info = response.json()
        print("Repository created:", repo_info.get("html_url", ""), flush=True)
        time.sleep(2)
    elif response.status_code == 200:
        repo_info = response.json()
        print("Repository already exists; uploading/updating project files in it.", flush=True)
    else:
        raise UploadError(f"Repository check failed: HTTP {response.status_code} {response.text[:500]}")

    branch = repo_info.get("default_branch") or "main"
    ref_path = f"{repo}/git/ref/heads/{quote(branch, safe='')}"
    response = api("GET", ref_path, token)
    parent = None
    base_tree = None
    if response.status_code == 200:
        parent = response.json()["object"]["sha"]
        response = api("GET", repo + "/git/commits/" + parent, token)
        if response.status_code != 200:
            raise UploadError(f"Could not read current branch commit: HTTP {response.status_code} {response.text[:500]}")
        base_tree = response.json()["tree"]["sha"]
    elif response.status_code != 404:
        raise UploadError(f"Could not read branch '{branch}': HTTP {response.status_code} {response.text[:500]}")

    print("\nPreparing and uploading source files...", flush=True)
    entries = entries_for(token, repo, files)
    message = f"TXT 2 SHORTS V{version}: upload Android project and GitHub Actions build"
    sha = commit(token, repo, branch, parent, base_tree, entries, message)
    actions_url = f"https://github.com/{username}/{repo_name}/actions"
    print("\nUPLOAD SUCCESSFUL", flush=True)
    print(f"Repository: https://github.com/{username}/{repo_name}", flush=True)
    print("Commit:", sha, flush=True)

    apk_path = wait_and_download(token, repo, sha, branch, actions_url)
    print("\n" + "=" * 68, flush=True)
    print("SUCCESS! APK downloaded to:", apk_path, flush=True)
    print("Transfer this APK to your Android phone and install it.", flush=True)
    print("=" * 68, flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        sys.exit(130)
    except Exception as exc:
        # Do NOT call sys.exit() here: it skips the final pause when this .py is
        # launched directly by double-clicking, which made the console vanish.
        message = f"\nERROR: {type(exc).__name__}: {exc}"
        print(message, flush=True)
        print("\nPAT safety: never share your token. Share only the error text or Actions log.", flush=True)
        traceback.print_exc()
        try:
            # Diagnostic file contains no PAT; it helps if the console is closed accidentally.
            with open(os.path.join(HERE, "github_uploader_error.log"), "a", encoding="utf-8") as log:
                log.write(message + "\n")
                log.write(traceback.format_exc() + "\n")
        except Exception:
            pass
    finally:
        # Always pause on success, API errors, and unexpected exceptions.
        try:
            input("\nPress Enter to close this window...")
        except EOFError:
            pass
