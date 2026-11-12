"""KOPIS performance-list collector; deliberately excludes posters and synopsis."""
from __future__ import annotations
import os, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import date
from typing import Any, Callable, Dict, List, Optional
from src.context.interest_matching import matches_interest
from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery
from src.sources.collectors.domestic_common import dated_status, parse_date

class KOPISCollector(BaseCollector):
    source_id="kopis"; ENDPOINT="http://www.kopis.or.kr/openApi/restful/pblprfr";MAX_ROWS=100
    # Verified against KOPIS's public PC detail pages.  This is deliberately
    # distinct from the OpenAPI detail endpoint: users receive a browser URL.
    PUBLIC_DETAIL_BASE="https://kopis.or.kr/por/db/pblprfr/pblprfrView.do"
    def __init__(self,fetch_text:Optional[Callable[[str,float,Dict[str,str]],str]]=None,timeout:float=8.0):self.fetch_text=fetch_text or self._fetch;self.timeout=timeout
    def collect(self,queries:List[SourceQuery],limit:int)->CollectorResult:
        key=os.environ.get("KOPIS_API_KEY","").strip()
        if not key:return CollectorResult(source=self.source_id,errors=["KOPIS_API_KEY is required; no request was made."],items=[])
        q=queries[0] if queries else SourceQuery(source=self.source_id,query="");p=q.params or {}
        if not p.get("stdate") or not p.get("eddate"):return CollectorResult(source=self.source_id,errors=["stdate and eddate are required; no request was made."],items=[])
        try:root=ET.fromstring(self.fetch_text(self._url(key,p,limit),self.timeout,{"Accept":"application/xml","User-Agent":"LUMOS/0.1"}))
        except ET.ParseError as exc:return CollectorResult(source=self.source_id,errors=[f"invalid XML response: {exc}"],items=[])
        except Exception as exc:return CollectorResult(source=self.source_id,errors=[f"network request failed: {exc}"],items=[])
        items=[];seen=set()
        for node in root.findall(".//db"):
            item=self._normalise(node,q)
            if not item or item.source_item_id in seen or not self._matches(item,q):continue
            seen.add(item.source_item_id);items.append(item)
            if len(items)>=limit:break
        return CollectorResult(source=self.source_id,items=items)
    def _url(self,key:str,p:Dict[str,Any],limit:int)->str:
        values={"service":key,"stdate":str(p["stdate"]),"eddate":str(p["eddate"]),"cpage":str(max(1,int(p.get("cpage") or 1))),"rows":str(min(max(1,limit),self.MAX_ROWS))}
        for name in ("shprfnm","shprfnmfct","shcate","signgucode","signgucodesub","prfstate","afterdate"):
            if p.get(name):values[name]=str(p[name])
        return self.ENDPOINT+"?"+urllib.parse.urlencode(values)
    @staticmethod
    def _text(n:ET.Element,name:str)->str:return (n.findtext(name) or "").strip()
    def _normalise(self,n:ET.Element,q:SourceQuery)->Optional[CollectedItem]:
        ident,title=self._text(n,"mt20id"),self._text(n,"prfnm")
        if not ident or not title:return None
        start,end=parse_date(self._text(n,"prfpdfrom")),parse_date(self._text(n,"prfpdto"));status=dated_status(start,end)
        if status=="ended":return None
        detail_url=self._public_detail_url(ident)
        return CollectedItem(source=self.source_id,source_item_id=ident,title=title[:300],url=detail_url,summary="",author="KOPIS",published_at=start,route_id=q.route_id,metrics_json={"content_kind":"performance","event_start_at":start,"event_end_at":end,"event_status":status,"venue":self._text(n,"fcltynm") or None,"region":self._text(n,"area") or None,"genre":self._text(n,"genrenm") or None,"source_url_status":"official_web_detail_pattern" if detail_url else "invalid_performance_id","official_detail_content_verified":False},raw_json={"performance_id":ident,"preserve_missing_published_at":True,"poster_collected":False,"synopsis_collected":False})

    @classmethod
    def _public_detail_url(cls, performance_id:str)->str:
        """Return only the documented KOPIS web-detail URL for a valid mt20id.

        A 200 page alone is not proof that an item exists; recommendation-time
        validation may still withhold a page whose actual detail content is not
        available.  The pattern prevents a feed value from selecting a host or
        path outside KOPIS.
        """
        ident=str(performance_id or "").strip()
        if not re.fullmatch(r"PF[0-9]{1,20}", ident):
            return ""
        return cls.PUBLIC_DETAIL_BASE+"?"+urllib.parse.urlencode({"mt20Id":ident})
    @staticmethod
    def _matches(item:CollectedItem,q:SourceQuery)->bool:
        interest=str((q.params or {}).get("raw_interest") or q.query or "").strip();return not interest or matches_interest(f"{item.title} {item.metrics_json.get('genre','')} {item.metrics_json.get('region','')}".casefold(),interest)
    @staticmethod
    def _fetch(url:str,timeout:float,headers:Dict[str,str])->str:
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=timeout) as r:return r.read(1_000_000).decode("utf-8",errors="replace")
