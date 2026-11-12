"""Work24 job-list collector using the documented XML list operation only."""
from __future__ import annotations
import os, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional
from src.context.interest_matching import matches_interest
from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery
from src.sources.collectors.domestic_common import dated_status, parse_date

class Work24Collector(BaseCollector):
    source_id="employment24"; ENDPOINT="https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"; MAX_PAGE_SIZE=100
    def __init__(self, fetch_text: Optional[Callable[[str,float,Dict[str,str]],str]]=None, timeout:float=8.0): self.fetch_text=fetch_text or self._fetch; self.timeout=timeout
    def collect(self, queries:List[SourceQuery], limit:int)->CollectorResult:
        key=os.environ.get("WORK24_API_KEY","").strip()
        if not key:return CollectorResult(source=self.source_id,errors=["WORK24_API_KEY is required; no request was made."],items=[])
        q=queries[0] if queries else SourceQuery(source=self.source_id,query="")
        try: root=ET.fromstring(self.fetch_text(self._url(key,q.params or {},limit),self.timeout,{"Accept":"application/xml","User-Agent":"LUMOS/0.1"}))
        except ET.ParseError as exc:return CollectorResult(source=self.source_id,errors=[f"invalid XML response: {exc}"],items=[])
        except Exception as exc:return CollectorResult(source=self.source_id,errors=[f"network request failed: {exc}"],items=[])
        items=[]; seen=set()
        for node in root.findall(".//wanted"):
            item=self._normalise(node,q)
            if not item or item.source_item_id in seen or not self._matches(item,q):continue
            seen.add(item.source_item_id);items.append(item)
            if len(items)>=limit:break
        return CollectorResult(source=self.source_id,items=items)
    def _url(self,key:str, params:Dict[str,Any],limit:int)->str:
        values={"authKey":key,"callTp":"L","returnType":"XML","startPage":str(max(1,int(params.get("page") or 1))),"display":str(min(max(1,limit),self.MAX_PAGE_SIZE))}
        for name in ("region","occupation","career","empTp","keyword","regDate","sortOrderBy"):
            if params.get(name):values[name]=str(params[name])
        return self.ENDPOINT+"?"+urllib.parse.urlencode(values)
    @staticmethod
    def _text(node:ET.Element,name:str)->str:return (node.findtext(name) or "").strip()
    def _normalise(self,node:ET.Element,q:SourceQuery)->Optional[CollectedItem]:
        ident,title=self._text(node,"wantedAuthNo"),self._text(node,"title")
        if not ident or not title:return None
        start,end=parse_date(self._text(node,"regDt")),parse_date(self._text(node,"closeDt")); status=dated_status(start,end)
        if status=="ended":return None
        return CollectedItem(source=self.source_id,source_item_id=ident,title=title[:300],url=self._text(node,"wantedInfoUrl"),summary="",author=self._text(node,"company")[:120],published_at=start,route_id=q.route_id,metrics_json={"content_kind":"job_posting","job_type":self._text(node,"career"),"region":self._text(node,"region"),"application_start_at":start,"application_end_at":end,"application_window_status":status},raw_json={"wanted_auth_no":ident,"preserve_missing_published_at":True,"information_provider":self._text(node,"infoSvc")})
    @staticmethod
    def _matches(item:CollectedItem,q:SourceQuery)->bool:
        interest=str((q.params or {}).get("raw_interest") or q.query or "").strip();return not interest or matches_interest(f"{item.title} {item.author}".casefold(),interest)
    @staticmethod
    def _fetch(url:str,timeout:float,headers:Dict[str,str])->str:
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=timeout) as r:return r.read(1_000_000).decode("utf-8",errors="replace")
