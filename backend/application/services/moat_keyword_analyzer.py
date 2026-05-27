from __future__ import annotations
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


KEYWORD_GROUPS: Dict[str, List[Dict[str, Any]]] = {
    "intangible_assets": [
        {"keywords": ["patent", "patents", "patented"], "weight": 0.9},
        {"keywords": ["trademark", "trademarks"], "weight": 0.8},
        {"keywords": ["copyright", "copyrights"], "weight": 0.8},
        {"keywords": ["intellectual property", "ip portfolio"], "weight": 0.9},
        {"keywords": ["brand", "brand recognition", "brand equity"], "weight": 0.7},
        {"keywords": ["license", "licenses", "licensing"], "weight": 0.6},
        {"keywords": ["regulatory approval", "fda approval"], "weight": 0.8},
        {"keywords": ["proprietary technology", "proprietary"], "weight": 0.7},
        {"keywords": ["research and development", "r&d"], "weight": 0.5},
    ],
    "switching_costs": [
        {"keywords": ["switching cost", "switching costs"], "weight": 1.0},
        {"keywords": ["high switching", "significant switching"], "weight": 1.0},
        {"keywords": ["customer retention", "retention rate"], "weight": 0.8},
        {"keywords": ["loyalty program", "customer loyalty"], "weight": 0.7},
        {"keywords": ["stickiness", "customer stickiness"], "weight": 0.9},
        {"keywords": ["recurring revenue", "subscription"], "weight": 0.7},
        {"keywords": ["long-term contract", "multi-year contract"], "weight": 0.8},
        {"keywords": ["integration cost", "implementation cost"], "weight": 0.7},
        {"keywords": ["vendor lock-in", "lock-in"], "weight": 0.9},
    ],
    "network_effects": [
        {"keywords": ["network effect", "network effects"], "weight": 1.0},
        {"keywords": ["platform effect", "platform economy"], "weight": 0.8},
        {"keywords": ["two-sided market", "multi-sided"], "weight": 0.9},
        {"keywords": ["user base", "user growth", "active users"], "weight": 0.7},
        {"keywords": ["ecosystem", "platform ecosystem"], "weight": 0.8},
        {"keywords": ["marketplace", "online marketplace"], "weight": 0.6},
        {"keywords": ["viral", "word of mouth"], "weight": 0.5},
        {"keywords": ["scale advantage", "scaling advantage"], "weight": 0.7},
    ],
    "cost_advantages": [
        {"keywords": ["low-cost producer", "cost leader"], "weight": 0.9},
        {"keywords": ["economies of scale", "scale economies"], "weight": 0.8},
        {"keywords": ["cost advantage", "cost advantage over"], "weight": 0.9},
        {"keywords": ["operating leverage", "operational leverage"], "weight": 0.7},
        {"keywords": ["efficient scale", "scale efficiency"], "weight": 0.7},
        {"keywords": ["location advantage", "geographic advantage"], "weight": 0.6},
        {"keywords": ["input cost", "raw material access"], "weight": 0.5},
        {"keywords": ["process innovation", "manufacturing efficiency"], "weight": 0.6},
    ],
    "scale_efficiencies": [
        {"keywords": ["distribution network", "distribution channel"], "weight": 0.7},
        {"keywords": ["supply chain", "supply chain advantage"], "weight": 0.7},
        {"keywords": ["largest", "leading", "market leader"], "weight": 0.6},
        {"keywords": ["market share", "market position"], "weight": 0.6},
        {"keywords": ["global presence", "global footprint"], "weight": 0.5},
        {"keywords": ["diversified", "diversification"], "weight": 0.4},
        {"keywords": ["high barriers", "barriers to entry"], "weight": 0.9},
    ],
}


class MoatKeywordAnalyzer:
    def __init__(self) -> None:
        self._compiled: Dict[str, List[Tuple[re.Pattern, float]]] = {}
        for group_name, entries in KEYWORD_GROUPS.items():
            compiled_list = []
            for entry in entries:
                for kw in entry["keywords"]:
                    pattern = re.compile(
                        rf"\b{re.escape(kw)}\b", re.IGNORECASE
                    )
                    compiled_list.append((pattern, entry["weight"]))
            self._compiled[group_name] = compiled_list

    def analyze(
        self,
        text: str,
        sections: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "groups_found": [],
            "total_matches": 0,
            "evidence": [],
            "group_scores": {},
        }

        text_lower = text.lower()
        text_len = len(text)
        if text_len < 100:
            return result

        for group_name, patterns in self._compiled.items():
            group_matches = []
            for pattern, weight in patterns:
                for match in pattern.finditer(text_lower):
                    start = max(0, match.start() - 100)
                    end = min(text_len, match.end() + 100)
                    snippet = text[start:end].strip()
                    snippet = re.sub(r"\s+", " ", snippet)
                    group_matches.append(
                        {
                            "keyword": match.group(),
                            "keyword_group": group_name,
                            "snippet": snippet,
                            "relevance_score": weight,
                            "position": match.start(),
                        }
                    )

            if group_matches:
                deduplicated = self._deduplicate_by_snippet(group_matches)
                result["groups_found"].append(group_name)
                result["evidence"].extend(deduplicated)
                result["total_matches"] += len(deduplicated)
                result["group_scores"][group_name] = round(
                    sum(m["relevance_score"] for m in deduplicated) / max(len(deduplicated), 1)
                    * min(len(deduplicated) / 3.0, 1.0),
                    4,
                )

        result["evidence"] = sorted(
            result["evidence"], key=lambda x: x["relevance_score"], reverse=True
        )
        return result

    def _deduplicate_by_snippet(
        self, matches: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        seen_snippets: set = set()
        unique = []
        for m in matches:
            snippet_key = m["snippet"][:80]
            if snippet_key not in seen_snippets:
                seen_snippets.add(snippet_key)
                unique.append(m)
        return unique

    def compute_stage2_score(
        self, analysis_result: Dict[str, Any]
    ) -> float:
        groups_found = analysis_result.get("groups_found", [])
        group_scores = analysis_result.get("group_scores", {})
        total_matches = analysis_result.get("total_matches", 0)

        if not groups_found or total_matches == 0:
            return 0.0

        avg_group_score = (
            sum(group_scores.values()) / len(group_scores)
            if group_scores
            else 0.0
        )

        coverage_ratio = len(groups_found) / max(len(KEYWORD_GROUPS), 1)
        match_density = min(total_matches / 20.0, 1.0)

        return round(
            (avg_group_score * 0.5) + (coverage_ratio * 0.3) + (match_density * 0.2) * 100,
            2,
        )
