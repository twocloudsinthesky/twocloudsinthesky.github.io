#!/usr/bin/env python3
"""Build a personal Apple Podcasts RSS feed from Xiaoyuzhou's public page."""

import argparse
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path


PODCAST_ID = "64c78b16e8176c3ff823e282"
SOURCE_URL = f"https://www.xiaoyuzhoufm.com/podcast/{PODCAST_ID}"
FEED_URL = "https://twocloudsinthesky.github.io/liye-podcast/feed.xml"
COVER_URL = "https://twocloudsinthesky.github.io/liye-podcast/cover.jpg"
ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"

ET.register_namespace("itunes", ITUNES)
ET.register_namespace("atom", ATOM)


def add(parent, name, value, attributes=None):
    element = ET.SubElement(parent, name, attributes or {})
    if value is not None:
        element.text = str(value)
    return element


def load_podcast(html):
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Xiaoyuzhou page did not contain podcast data")
    podcast = json.loads(match.group(1))["props"]["pageProps"]["podcast"]
    if podcast["pid"] != PODCAST_ID:
        raise ValueError("Unexpected podcast ID")
    return podcast


def build(podcast):
    episodes = sorted(podcast["episodes"], key=lambda e: e["pubDate"], reverse=True)
    if len(episodes) < 11:
        raise ValueError("Source page returned fewer than the 11 known episodes")

    root = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(root, "channel")
    add(channel, "title", podcast["title"])
    add(channel, "link", SOURCE_URL)
    add(channel, "description", podcast["description"])
    add(channel, "language", "zh-CN")
    add(channel, "lastBuildDate", format_datetime(datetime.fromisoformat(episodes[0]["pubDate"].replace("Z", "+00:00")), usegmt=True))
    add(channel, f"{{{ATOM}}}link", None, {"href": FEED_URL, "rel": "self", "type": "application/rss+xml"})
    add(channel, f"{{{ITUNES}}}author", podcast["author"])
    add(channel, f"{{{ITUNES}}}summary", podcast["description"])
    add(channel, f"{{{ITUNES}}}image", None, {"href": COVER_URL})
    add(channel, f"{{{ITUNES}}}type", "episodic")
    add(channel, f"{{{ITUNES}}}category", None, {"text": "Society & Culture"})
    add(channel, f"{{{ITUNES}}}block", "Yes")
    add(channel, "generator", "Personal Xiaoyuzhou RSS mirror")
    add(channel, "image", None)
    image = channel.find("image")
    add(image, "url", COVER_URL)
    add(image, "title", podcast["title"])
    add(image, "link", SOURCE_URL)

    seen_guids = set()
    seen_urls = set()
    for index, episode in enumerate(episodes):
        eid = episode["eid"]
        media = episode["media"]
        url = episode["enclosure"]["url"]
        if eid in seen_guids or url in seen_urls:
            raise ValueError("Duplicate episode ID or enclosure URL")
        if not url.startswith("https://media.xyzcdn.net/") or not url.endswith(".m4a"):
            raise ValueError(f"Unexpected audio URL: {url}")
        if media["size"] <= 0 or episode["duration"] <= 0:
            raise ValueError(f"Missing size or duration for episode {eid}")
        seen_guids.add(eid)
        seen_urls.add(url)

        item = ET.SubElement(channel, "item")
        episode_url = f"https://www.xiaoyuzhoufm.com/episode/{eid}"
        add(item, "title", episode["title"])
        add(item, "link", episode_url)
        add(item, "description", episode["title"])
        add(item, "guid", f"urn:xiaoyuzhou:episode:{eid}", {"isPermaLink": "false"})
        published = datetime.fromisoformat(episode["pubDate"].replace("Z", "+00:00"))
        add(item, "pubDate", format_datetime(published, usegmt=True))
        add(item, "enclosure", None, {"url": url, "length": str(media["size"]), "type": "audio/mp4"})
        add(item, f"{{{ITUNES}}}duration", episode["duration"])
        add(item, f"{{{ITUNES}}}episode", len(episodes) - index)
        add(item, f"{{{ITUNES}}}episodeType", "full")

    ET.indent(root, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8") + b"\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, help="Use a previously downloaded page")
    parser.add_argument("--output", type=Path, default=Path("feed.xml"))
    args = parser.parse_args()
    if args.html:
        html = args.html.read_text(encoding="utf-8")
    else:
        request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8")
    podcast = load_podcast(html)
    feed = build(podcast)
    if args.output.exists():
        fresh = ET.fromstring(feed)
        old = ET.parse(args.output).getroot()
        fresh_channel = fresh.find("channel")
        old_channel = old.find("channel")
        known_guids = {item.findtext("guid") for item in fresh_channel.findall("item")}
        known_urls = {item.find("enclosure").get("url") for item in fresh_channel.findall("item")}
        for item in old_channel.findall("item"):
            guid = item.findtext("guid")
            enclosure = item.find("enclosure")
            url = enclosure.get("url") if enclosure is not None else None
            if guid and url and guid not in known_guids and url not in known_urls:
                fresh_channel.append(item)
                known_guids.add(guid)
                known_urls.add(url)
        ET.indent(fresh, space="  ")
        feed = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(fresh, encoding="utf-8") + b"\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(feed)
    print(f"Wrote {args.output} with {len(podcast['episodes'])} episodes")


if __name__ == "__main__":
    main()
