from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def article_key(item):
    url = item.get("url") or item.get("source_url") or ""
    if url:
        parts = urlsplit(url)
        query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                 if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
        return urlunsplit(("https", parts.netloc.lower().removeprefix("www."), parts.path.rstrip("/"), urlencode(sorted(query)), ""))
    return (item.get("source"), item.get("source_item_id") or item.get("id"))
