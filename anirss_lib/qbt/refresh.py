"""Let qBittorrent poll feeds of on-demand endpoints while they are up.

qBittorrent keeps owning the subscription (feed + auto-download rule), but
it can only fetch an on-demand feed, and the download links in it, while
the endpoint's service runs. So the service is brought up, the feeds are
refreshed, and we wait for qBittorrent to finish matching and adding
before the service may go down again.
"""

import os
import time

from anirss_lib import ondemand
from anirss_lib.ansi import C_DIM, C_GRN, C_OFF, C_YEL
from anirss_lib.logging import log
from anirss_lib.qbt.session import QbtSession

POLL_S = 1.0
FEED_TIMEOUT_S = 180.0
ADD_TIMEOUT_S = 90.0
QUIET_S = 6.0


def _walk_feeds(node, prefix: str = "") -> dict[str, dict]:
    """Flatten qB's nested rss/items tree into {path: feed}."""
    out: dict[str, dict] = {}
    if not isinstance(node, dict):
        return out
    for key, child in node.items():
        if not isinstance(child, dict):
            continue
        if isinstance(child.get("url"), str):
            out[f"{prefix}{key}"] = child
        else:
            out.update(_walk_feeds(child, f"{prefix}{key}\\"))
    return out


def feeds(qbt: QbtSession, *, with_data: bool = False) -> dict[str, dict]:
    return _walk_feeds(qbt.get_json("/api/v2/rss/items",
                                    withData="true" if with_data else "false"))


def on_demand_feeds(qbt: QbtSession, endpoints) -> list[tuple[object, list[str]]]:
    """[(endpoint, [feed paths])] for every on-demand endpoint that has at
    least one subscribed feed."""
    all_feeds = feeds(qbt)
    out = []
    for ep in endpoints:
        if not ep.on_demand:
            continue
        paths = [p for p, f in all_feeds.items() if ep.owns_url(f["url"])]
        if paths:
            out.append((ep, paths))
    return out


def _hashes(qbt: QbtSession) -> set[str]:
    info = qbt.get_json("/api/v2/torrents/info")
    return {t["hash"] for t in info if isinstance(t, dict) and "hash" in t}


def _pending_matches(qbt: QbtSession, urls: set[str], titles_unread: set[str]
                     ) -> int:
    """How many articles the auto-downloader has matched but not processed
    yet (qB marks an article read once it hands it to the downloader)."""
    rules = qbt.get_json("/api/v2/rss/rules")
    pending = 0
    for name, rule in (rules or {}).items():
        if not rule.get("enabled") or not urls & set(rule.get("affectedFeeds") or []):
            continue
        matched = qbt.get_json("/api/v2/rss/matchingArticles", ruleName=name)
        for titles in (matched or {}).values():
            pending += sum(1 for t in titles if t in titles_unread)
    return pending


def settle(qbt: QbtSession, paths: list[str], *, refresh: bool = True) -> int:
    """Refresh `paths`, wait until qB has fetched them, processed the rule
    matches and added the resulting torrents. Returns how many torrents
    were added meanwhile."""
    before = _hashes(qbt)
    started = time.monotonic()
    if refresh:
        for path in paths:
            qbt.post("/api/v2/rss/refreshItem", itemPath=path)
        time.sleep(2 * POLL_S)

    deadline = started + FEED_TIMEOUT_S
    while True:
        data = {p: f for p, f in feeds(qbt, with_data=True).items() if p in paths}
        loading = [p for p, f in data.items() if f.get("isLoading")]
        if not loading or time.monotonic() > deadline:
            break
        time.sleep(POLL_S)
    for p, f in data.items():
        if f.get("hasError"):
            log("WARN", f"refresh: feed {p!r} reported an error")

    urls = {f["url"] for f in data.values()}
    unread = {a.get("title", "") for f in data.values()
              for a in f.get("articles") or [] if not a.get("isRead")}
    deadline = time.monotonic() + ADD_TIMEOUT_S
    while unread and _pending_matches(qbt, urls, unread):
        if time.monotonic() > deadline:
            log("WARN", "refresh: matches still unprocessed at timeout")
            break
        time.sleep(POLL_S)
        data = {p: f for p, f in feeds(qbt, with_data=True).items() if p in paths}
        unread = {a.get("title", "") for f in data.values()
                  for a in f.get("articles") or [] if not a.get("isRead")}

    # Downloads of matched articles resolve asynchronously (the link has to
    # be fetched through the service); wait until the torrent list has been
    # quiet for a while.
    last, quiet_since = _hashes(qbt), time.monotonic()
    deadline = time.monotonic() + ADD_TIMEOUT_S
    while time.monotonic() - quiet_since < QUIET_S and time.monotonic() < deadline:
        time.sleep(POLL_S)
        now = _hashes(qbt)
        if now != last:
            last, quiet_since = now, time.monotonic()
    added = len(last - before)
    log("INFO", f"refresh: {len(paths)} feed(s) settled in "
                f"{time.monotonic() - started:.0f}s, {added} torrent(s) added")
    return added


def cmd_refresh_on_demand(qbt_cfg, endpoints) -> None:
    """The hourly job: start each on-demand endpoint that has subscriptions,
    let qB poll its feeds, stop it again. Silent when there is nothing to do."""
    from anirss_lib.qbt.session import _qbt_reachable, login_with_password

    if not any(ep.on_demand for ep in endpoints):
        return
    if not _qbt_reachable(qbt_cfg["url"]):
        log("INFO", "refresh: qBittorrent not running, nothing to do")
        return
    qbt = login_with_password(qbt_cfg, os.environ.get("ANIRSS_QBT_PASSWORD", ""))
    for ep, paths in on_demand_feeds(qbt, endpoints):
        t0 = time.monotonic()
        try:
            ondemand.ensure(ep)
        except ondemand.StartError as e:
            print(f"{C_YEL}{e}{C_OFF}")
            continue
        try:
            added = settle(qbt, paths)
        finally:
            ondemand.release(ep)
        print(f"{C_GRN}{ep.name}:{C_OFF} refreshed {len(paths)} feed(s), "
              f"{added} new torrent(s) {C_DIM}({time.monotonic() - t0:.0f}s){C_OFF}")
