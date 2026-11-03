import requests
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

def get_project_name(url):
    """
    Extract the project name from a SourceForge URL.
    Example: https://sourceforge.net/p/sempublishing/code/... → 'sempublishing'
    """
    match = re.search(r'sourceforge\.net/p/([^/]+)/', url)
    if match:
        return match.group(1)
    raise ValueError("Couldn't parse project name from URL")

def get_project_info(project):
    """
    Fetch basic project info and license from SourceForge API.
    """
    api_url = f"https://sourceforge.net/rest/p/{project}"
    r = requests.get(api_url)
    r.raise_for_status()
    return r.json()

def get_project_releases(project):
    """
    Fetch project release RSS feed.
    """
    rss_url = f"https://sourceforge.net/projects/{project}/rss?path=/"
    r = requests.get(rss_url)
    if r.status_code != 200:
        return []
    root = ET.fromstring(r.content)
    releases = []
    for item in root.findall(".//item"):
        releases.append({
            "title": item.findtext("title"),
            "link": item.findtext("link"),
            "pubDate": item.findtext("pubDate")
        })
    return releases

def get_file_history(project, filepath):
    """
    Fetch file history (user + dates) using SVN log API.
    """
    api_url = f"https://sourceforge.net/rest/p/{project}/svn/log/{filepath.lstrip('/')}"
    r = requests.get(api_url)
    if r.status_code != 200:
        return {"error": f"Unable to retrieve file history ({r.status_code})"}
    try:
        logs = r.json()
        history = []
        for entry in logs.get("log", []):
            history.append({
                "revision": entry.get("revision"),
                "author": entry.get("author"),
                "date": entry.get("date"),
                "message": entry.get("msg")
            })
        return history
    except Exception as e:
        return {"error": str(e)}

def extract_file_path(url):
    """
    Extract the file path within the repo from a SourceForge code URL.
    Example: https://sourceforge.net/p/sempublishing/code/HEAD/tree/SPAR/BIBO2SPAR.ttl
    → SPAR/BIBO2SPAR.ttl
    """
    match = re.search(r'/code/HEAD/tree/(.*?)(?:\?|$)', url)
    if match:
        return match.group(1)
    return None

def get_sourceforge_metadata(url):
    project = get_project_name(url)
    project_info = get_project_info(project)
    releases = get_project_releases(project)

    file_path = extract_file_path(url)
    file_history = get_file_history(project, file_path) if file_path else None

    metadata = {
        "project": project,
        "project_info": project_info,
        "releases": releases,
        "file_path": file_path,
        "file_history": file_history
    }
    return metadata

if __name__ == "__main__":
    # Example usage
    test_url = "https://sourceforge.net/p/sempublishing/code/HEAD/tree/SPAR/BIBO2SPAR.ttl?format=raw"
    metadata = get_sourceforge_metadata(test_url)
    print(json.dumps(metadata, indent=2))
