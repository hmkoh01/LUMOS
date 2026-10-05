from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def article_key(item):
    url = item.get("url") or item.get("source_url") or ""
    if url:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().removeprefix("www.")
        video_id = ""
        if host == "youtu.be":
            video_id = parts.path.strip("/").split("/")[0]
        elif host == "youtube.com" or host.endswith(".youtube.com"):
            if parts.path == "/watch":
                video_id = dict(parse_qsl(parts.query)).get("v", "")
            elif parts.path.startswith(("/shorts/", "/embed/", "/live/")):
                video_id = parts.path.split("/")[2]
        if video_id:
            return "https://youtube.com/watch?" + urlencode({"v": video_id})
        query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                 if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
        return urlunsplit(("https", parts.netloc.lower().removeprefix("www."), parts.path.rstrip("/"), urlencode(sorted(query)), ""))
    return (item.get("source"), item.get("source_item_id") or item.get("id"))
