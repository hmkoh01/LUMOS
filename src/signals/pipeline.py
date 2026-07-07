from typing import Any, Dict, List, Optional

from src.signals.candidate import CandidateBuilder
from src.signals.generator import SignalGenerator
from src.signals.ranking import RankingService
from src.sources.collector_registry import CollectorRegistry
from src.sources.collectors.base import SourceQuery
from src.sources.query_planner import QueryPlanner
from src.sources.router import SourceRouter
from src.storage.sqlite_store import SQLiteStore


class SignalPipeline:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def preview_routes(self) -> List[Dict[str, Any]]:
        profile, settings, connectors, interests, source_configs = self._load_context()
        routes = SourceRouter().plan(profile, settings, connectors, interests, source_configs=source_configs)
        return QueryPlanner().build_queries(routes, profile, interests)

    def collect_mock(self, triggered_by: str = "manual") -> Dict[str, Any]:
        return self.collect_sources(mode="mock", triggered_by=triggered_by)

    def collect_sources(self, mode: str = "mock", triggered_by: str = "manual") -> Dict[str, Any]:
        profile, settings, connectors, interests, source_configs = self._load_context()
        planned = QueryPlanner().build_queries(
            SourceRouter().plan(profile, settings, connectors, interests, source_configs=source_configs),
            profile,
            interests,
        )
        selected_sources = sorted({route["source"] for route in planned})
        run_id = self.store.create_pipeline_run(
            "mock_collection" if mode == "mock" else "source_collection",
            triggered_by=triggered_by,
            settings_snapshot=settings,
            profile_snapshot=profile,
            interest_snapshot=interests,
            selected_sources=selected_sources,
        )

        try:
            persisted = self.persist_routes(planned, pipeline_run_id=run_id)
            collection = self.collect_source_items(persisted, pipeline_run_id=run_id, mode=mode)
            summary = {
                "selected_sources": collection["selected_sources"],
                "attempted_sources": collection["attempted_sources"],
                "successful_sources": collection["successful_sources"],
                "failed_sources": collection["failed_sources"],
                "errors_by_source": collection["errors_by_source"],
                "skipped_sources": collection["skipped_sources"],
                "disabled_sources": collection["disabled_sources"],
                "missing_config_sources": collection["missing_config_sources"],
                "route_count": len(persisted),
                "collected_item_count": len(collection["source_items"]),
            }
            self.store.complete_pipeline_run(run_id, summary)
            return {"pipeline_run_id": run_id, **collection}
        except Exception as exc:
            self.store.fail_pipeline_run(run_id, str(exc))
            raise

    def generate_daily_signals(
        self,
        replace_today: bool = True,
        triggered_by: str = "manual",
        mode: str = "mock",
        run_type: str = "signal_generation",
    ) -> Dict[str, Any]:
        profile, settings, connectors, interests, source_configs = self._load_context()
        planned = QueryPlanner().build_queries(
            SourceRouter().plan(profile, settings, connectors, interests, source_configs=source_configs),
            profile,
            interests,
        )
        selected_sources = sorted({route["source"] for route in planned})
        run_id = self.store.create_pipeline_run(
            run_type,
            triggered_by=triggered_by,
            settings_snapshot=settings,
            profile_snapshot=profile,
            interest_snapshot=interests,
            selected_sources=selected_sources,
        )

        try:
            persisted = self.persist_routes(planned, pipeline_run_id=run_id)
            collection = self.collect_source_items(persisted, pipeline_run_id=run_id, mode=mode)
            candidates = CandidateBuilder(self.store).create_from_source_items(
                collection["source_items"],
                interests,
                pipeline_run_id=run_id,
            )
            ranked = RankingService(self.store).rank(candidates)
            signals = SignalGenerator(self.store).generate_from_candidates(
                ranked,
                replace_today=replace_today,
                pipeline_run_id=run_id,
                archive_reason=f"replaced_by_run:{run_id}" if replace_today else None,
            )
            signal_count = max(1, int(settings.get("signal_count", 3)))
            summary = {
                "selected_sources": collection["selected_sources"],
                "attempted_sources": collection["attempted_sources"],
                "successful_sources": collection["successful_sources"],
                "failed_sources": collection["failed_sources"],
                "errors_by_source": collection["errors_by_source"],
                "skipped_sources": collection["skipped_sources"],
                "disabled_sources": collection["disabled_sources"],
                "missing_config_sources": collection["missing_config_sources"],
                "route_count": len(persisted),
                "collected_item_count": len(collection["source_items"]),
                "candidate_count": len(candidates),
                "signal_count": len(signals),
                "replace_today": replace_today,
                "mode": mode,
            }
            self.store.complete_pipeline_run(run_id, summary)
            return {
                "pipeline_run_id": run_id,
                "selected_sources": collection["selected_sources"],
                "attempted_sources": collection["attempted_sources"],
                "successful_sources": collection["successful_sources"],
                "failed_sources": collection["failed_sources"],
                "errors_by_source": collection["errors_by_source"],
                "skipped_sources": collection["skipped_sources"],
                "disabled_sources": collection["disabled_sources"],
                "missing_config_sources": collection["missing_config_sources"],
                "collected_item_count": len(collection["source_items"]),
                "routes": persisted,
                "source_items": collection["source_items"],
                "top_candidates": ranked[:signal_count],
                "signals": signals,
            }
        except Exception as exc:
            self.store.fail_pipeline_run(run_id, str(exc))
            raise

    def persist_routes(
        self,
        planned_routes: List[Dict[str, Any]],
        pipeline_run_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        persisted = []
        for route in planned_routes:
            query_entries = route.get("queries") or [{"query": "", "params": {}}]
            for query in query_entries:
                route_id = self.store.create_source_route(
                    {
                        "route_date": route["route_date"],
                        "source": route["source"],
                        "query": query["query"],
                        "limit_count": route["collection_limit"],
                        "reason": route["reason"],
                        "category": route["category"],
                        "status": "planned",
                    },
                    pipeline_run_id=pipeline_run_id,
                )
                persisted.append(
                    {
                        **route,
                        "pipeline_run_id": pipeline_run_id,
                        "route_id": route_id,
                        "queries": [query],
                    }
                )
        return persisted

    def collect_mock_items(
        self,
        planned_routes: List[Dict[str, Any]],
        pipeline_run_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.collect_source_items(planned_routes, pipeline_run_id=pipeline_run_id, mode="mock")

    def collect_source_items(
        self,
        planned_routes: List[Dict[str, Any]],
        pipeline_run_id: Optional[int] = None,
        mode: str = "mock",
    ) -> Dict[str, Any]:
        registry = CollectorRegistry()
        source_configs = self.store.get_source_configs()
        config_map = {item["source_id"]: item for item in source_configs}
        raw_items = []
        errors_by_source: Dict[str, List[str]] = {}
        attempted_sources = []
        successful_sources = []
        failed_sources = []
        selected_sources = sorted({route["source"] for route in planned_routes})
        disabled_sources = sorted(item["source_id"] for item in source_configs if not item["enabled"])
        skipped_sources = sorted(set(config_map) - set(selected_sources) - set(disabled_sources))
        missing_config_sources = []

        for route in planned_routes:
            source = route["source"]
            if self._missing_required_source_config(source, route, mode):
                missing_config_sources.append(source)
            attempted_sources.append(source)
            queries = self._source_queries(route)
            result = registry.collect(
                source,
                queries,
                limit=max(1, int(route.get("collection_limit", 5))),
                mode=mode,
            )
            if result.errors or result.warnings:
                errors_by_source.setdefault(source, []).extend(result.errors + result.warnings)
            if result.items:
                successful_sources.append(source)
                raw_items.extend(result.item_dicts())
            elif result.errors or result.warnings:
                failed_sources.append(source)

        saved_items = []
        for item in raw_items:
            item_id = self.store.upsert_source_item(item, pipeline_run_id=pipeline_run_id)
            saved = self.store.get_source_item(item_id)
            if saved:
                saved["pipeline_run_id"] = pipeline_run_id
                saved["route_id"] = item.get("route_id")
                saved["route_category"] = item.get("raw_json", {}).get("route", {}).get("category", "")
                saved_items.append(saved)
        return {
            "routes": planned_routes,
            "source_items": saved_items,
            "selected_sources": selected_sources,
            "attempted_sources": sorted(set(attempted_sources)),
            "successful_sources": sorted(set(successful_sources)),
            "failed_sources": sorted(set(failed_sources)),
            "errors_by_source": errors_by_source,
            "skipped_sources": skipped_sources,
            "disabled_sources": disabled_sources,
            "missing_config_sources": sorted(set(missing_config_sources)),
        }

    def _source_queries(self, route: Dict[str, Any]) -> List[SourceQuery]:
        queries = []
        for query in route.get("queries") or []:
            queries.append(
                SourceQuery(
                    source=route["source"],
                    query=query.get("query", ""),
                    params=query.get("params", {}),
                    route_id=route.get("route_id"),
                    route_date=route.get("route_date"),
                    category=route.get("category", ""),
                    reason=route.get("reason", ""),
                )
            )
        return queries

    def _missing_required_source_config(self, source: str, route: Dict[str, Any], mode: str) -> bool:
        if mode == "mock" or source not in {"rss", "official_ai_blogs", "company_newsroom"}:
            return False
        for query in route.get("queries") or []:
            params = query.get("params", {})
            if params.get("feed_url") or params.get("url") or params.get("feed_urls"):
                return False
            if str(query.get("query", "")).startswith("http"):
                return False
        return True

    def _load_context(self):
        profile = self.store.get_profile() or {}
        settings = self.store.get_settings()
        connectors = self.store.get_connectors()
        interests = self.store.get_interests(limit=50)
        source_configs = self.store.get_source_configs()
        return profile, settings, connectors, interests, source_configs
