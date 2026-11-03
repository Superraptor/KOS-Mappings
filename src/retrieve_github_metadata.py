import requests
import sys
import json
from urllib.parse import urlparse

GITHUB_API = "https://api.github.com/repos"


def get_repo_file_metadata(url: str):
    """
    Given a GitHub repo, file, or raw link, fetch metadata including:
      - Repo metadata (with license)
      - File metadata (size, sha, download_url, etc.)
      - Contributors (user + date for file commits)
    """
    parsed = urlparse(url)
    if "github.com" not in parsed.netloc and "raw.githubusercontent.com" not in parsed.netloc:
        raise ValueError("Not a valid GitHub URL")

    # Normalize raw.githubusercontent.com to GitHub API format
    if "raw.githubusercontent.com" in parsed.netloc:
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4:
            raise ValueError("Invalid raw GitHub URL")
        user, repo, branch, *filepath = parts
        repo_api_url = f"{GITHUB_API}/{user}/{repo}"
        file_api_url = f"{repo_api_url}/contents/{'/'.join(filepath)}?ref={branch}"
        commits_api_url = f"{repo_api_url}/commits?path={'/'.join(filepath)}&sha={branch}"
    else:
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError("Invalid GitHub URL")

        user, repo, *rest = parts
        repo_api_url = f"{GITHUB_API}/{user}/{repo}"

        if "blob" in rest:
            branch = rest[1]
            filepath = rest[2:]
            file_api_url = f"{repo_api_url}/contents/{'/'.join(filepath)}?ref={branch}"
            commits_api_url = f"{repo_api_url}/commits?path={'/'.join(filepath)}&sha={branch}"
        else:
            file_api_url = None
            commits_api_url = None

    headers = {"Accept": "application/vnd.github.v3+json"}

    result = {}

    # Repo metadata (with license)
    repo_resp = requests.get(repo_api_url, headers=headers)
    if repo_resp.status_code != 200:
        raise Exception(f"Repo metadata fetch failed: {repo_resp.text}")
    repo_data = repo_resp.json()
    result["repo_metadata"] = repo_data

    # License info (if available)
    license_resp = requests.get(f"{repo_api_url}/license", headers=headers)
    if license_resp.status_code == 200:
        result["repo_license"] = license_resp.json()
    else:
        result["repo_license"] = {"error": "No license detected"}

    # File metadata (if applicable)
    if file_api_url:
        file_resp = requests.get(file_api_url, headers=headers)
        if file_resp.status_code == 200:
            result["file_metadata"] = file_resp.json()

        # File commit history (contributors + dates)
        commits_resp = requests.get(commits_api_url, headers=headers)
        if commits_resp.status_code == 200:
            commits_data = commits_resp.json()
            contributors = []
            for commit in commits_data:
                contributors.append({
                    "author": commit.get("commit", {}).get("author", {}).get("name"),
                    "author_email": commit.get("commit", {}).get("author", {}).get("email"),
                    "date": commit.get("commit", {}).get("author", {}).get("date"),
                    "username": commit.get("author", {}).get("login") if commit.get("author") else None,
                    "commit_url": commit.get("html_url")
                })
            result["file_contributors"] = contributors

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python github_metadata.py <github_url>")
        sys.exit(1)

    url = sys.argv[1]
    try:
        metadata = get_repo_file_metadata(url)
        print(json.dumps(metadata, indent=2))
    except Exception as e:
        print(f"Error: {e}")
