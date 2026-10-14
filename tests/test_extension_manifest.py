"""Guards for mistakes that silently stop the extension from attaching to the dashboard."""
import json
import re
from pathlib import Path

MANIFEST = json.loads((Path(__file__).parent.parent / "extension" / "manifest.json").read_text())

LOCAL_PAGES = {"http://127.0.0.1/*", "http://localhost/*"}


def patterns():
    yield from MANIFEST.get("host_permissions", [])
    for script in MANIFEST.get("content_scripts", []):
        yield from script["matches"]


def test_no_match_pattern_contains_a_port():
    # Firefox and Zen match nothing for "http://localhost:8765/*". A pattern without
    # a port matches any port in both Chrome and Firefox.
    with_port = [p for p in patterns() if re.match(r"^[^:]+://[^/]+:\d+", p)]
    assert not with_port, with_port


def test_dashboard_script_only_runs_on_local_pages():
    for script in MANIFEST["content_scripts"]:
        assert set(script["matches"]) == LOCAL_PAGES


def test_extension_can_reach_every_site_it_reads():
    hosts = set(MANIFEST["host_permissions"])
    assert {"https://us.prairielearn.com/*", "https://www.gradescope.com/*"} <= hosts
    assert LOCAL_PAGES <= hosts


def test_firefox_id_is_set_so_permissions_survive_reloads():
    assert MANIFEST["browser_specific_settings"]["gecko"]["id"]
