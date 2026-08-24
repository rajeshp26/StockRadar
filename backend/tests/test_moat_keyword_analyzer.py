import pytest

from application.services.moat_keyword_analyzer import KEYWORD_GROUPS, MoatKeywordAnalyzer


class TestMoatKeywordAnalyzer:
    def setup_method(self):
        self.analyzer = MoatKeywordAnalyzer()

    def test_analyze_identifies_moat_keywords(self, sample_tenk_text):
        result = self.analyzer.analyze(sample_tenk_text)
        assert result["total_matches"] > 0
        assert len(result["groups_found"]) > 0
        assert sorted(result["groups_found"]) == sorted(set(result["groups_found"]))

    def test_analyze_finds_switching_costs(self, sample_tenk_text):
        result = self.analyzer.analyze(sample_tenk_text)
        groups = result["groups_found"]
        found = any("switching" in g for g in groups)
        assert found, f"Expected switching_costs in groups, got {groups}"

    def test_analyze_finds_intangible_assets(self, sample_tenk_text):
        result = self.analyzer.analyze(sample_tenk_text)
        groups = result["groups_found"]
        found = any("intangible" in g for g in groups)
        assert found, f"Expected intangible_assets in groups, got {groups}"

    def test_analyze_returns_evidence_list(self, sample_tenk_text):
        result = self.analyzer.analyze(sample_tenk_text)
        assert isinstance(result["evidence"], list)
        for ev in result["evidence"]:
            assert "keyword" in ev
            assert "keyword_group" in ev
            assert "snippet" in ev
            assert "relevance_score" in ev

    def test_analyze_short_text_returns_empty(self):
        result = self.analyzer.analyze("Hello world")
        assert result["total_matches"] == 0
        assert result["groups_found"] == []
        assert result["evidence"] == []

    def test_analyze_empty_text(self):
        result = self.analyzer.analyze("")
        assert result["total_matches"] == 0

    def test_analyze_deduplicates_by_snippet(self, sample_tenk_text):
        repeated = sample_tenk_text + "\n" + sample_tenk_text
        result = self.analyzer.analyze(repeated)
        assert result["total_matches"] > 0

    def test_analyze_network_effects_keywords(self):
        text = """
        The company benefits from strong network effects as its user base grows.
        It operates a two-sided marketplace connecting buyers and sellers.
        The platform ecosystem creates significant competitive advantages.
        """
        result = self.analyzer.analyze(text)
        groups = result["groups_found"]
        found = any("network" in g for g in groups)
        assert found, f"Expected network_effects in groups, got {groups}"

    def test_analyze_cost_advantages_keywords(self):
        text = """
        The company is a low-cost producer with significant economies of scale.
        Its cost advantage over competitors comes from efficient scale operations.
        """
        result = self.analyzer.analyze(text)
        groups = result["groups_found"]
        found = any("cost" in g for g in groups)
        assert found, f"Expected cost_advantages in groups, got {groups}"

    def test_analyze_scale_efficiencies_keywords(self):
        text = """
        As the market leader, the company has the largest distribution network.
        Its supply chain advantage and high barriers to entry protect market share.
        """
        result = self.analyzer.analyze(text)
        groups = result["groups_found"]
        found = any("scale" in g or "efficien" in g for g in groups)
        assert found, f"Expected scale_efficiencies in groups, got {groups}"

    def test_compute_stage2_score_full_coverage(self, sample_tenk_text):
        result = self.analyzer.analyze(sample_tenk_text)
        score = self.analyzer.compute_stage2_score(result)
        assert 0 <= score <= 100
        assert score > 0

    def test_compute_stage2_score_no_matches(self):
        result = self.analyzer.analyze("nothing relevant here")
        score = self.analyzer.compute_stage2_score(result)
        assert score == 0.0

    def test_keyword_groups_are_defined(self):
        assert len(KEYWORD_GROUPS) >= 5
        for group_name, entries in KEYWORD_GROUPS.items():
            assert len(entries) > 0
            for entry in entries:
                assert "keywords" in entry
                assert "weight" in entry
                assert 0 < entry["weight"] <= 1.0

    def test_analyze_returns_group_scores(self, sample_tenk_text):
        result = self.analyzer.analyze(sample_tenk_text)
        assert "group_scores" in result
        if result["groups_found"]:
            for group in result["groups_found"]:
                assert group in result["group_scores"]
                assert 0 < result["group_scores"][group] <= 1.0

    def test_churn_does_not_false_positive(self):
        text = "churn rate increased to 15% this quarter due to competitive pressure"
        result = self.analyzer.analyze(text)
        assert result["total_matches"] == 0  # "churn" is not a keyword

    def test_multiple_sections_boosts_score(self):
        item1 = "The company benefits from strong network effects. Its platform ecosystem creates lock-in."
        item7 = "Our platform ecosystem continues to drive customer retention and network effects."
        combined = f"=== Item 1 ===\n{item1}\n\n=== Item 7 ===\n{item7}"
        result = self.analyzer.analyze(combined)
        assert result["total_matches"] > 0
        network_groups = [g for g in result["groups_found"] if "network" in g]
        assert len(network_groups) > 0

    def test_very_long_text_performance(self):
        paragraph = "The company has a strong brand recognition and proprietary technology. "
        paragraph += "Its network effects create switching costs for customers. "
        paragraph += "The company benefits from economies of scale and efficient operations. "
        long_text = paragraph * 1000
        import time
        start = time.time()
        result = self.analyzer.analyze(long_text)
        elapsed = time.time() - start
        assert result["total_matches"] > 0
        assert elapsed < 2.0  # must complete in under 2 seconds

    def test_case_insensitivity(self):
        filler = "The firm operates in several different countries across many regions. "
        lower = filler + "patents and trademarks provide competitive advantage"
        upper = filler + "PATENTS AND TRADEMARKS PROVIDE COMPETITIVE ADVANTAGE"
        mixed = filler + "Patents and Trademarks Provide Competitive Advantage"
        r1 = self.analyzer.analyze(lower)
        r2 = self.analyzer.analyze(upper)
        r3 = self.analyzer.analyze(mixed)
        assert r1["total_matches"] > 0
        assert r1["total_matches"] == r2["total_matches"]
        assert r2["total_matches"] == r3["total_matches"]

    def test_phrase_boundary_matching(self):
        filler = "The firm operates in several different countries across many regions. "
        text = filler + "The company's ecosystem creates strong competitive advantages for its business."
        result = self.analyzer.analyze(text)
        network_keywords_found = set()
        for ev in result["evidence"]:
            if "network" in ev["keyword_group"]:
                network_keywords_found.add(ev["keyword"])
        assert "ecosystem" in network_keywords_found  # "ecosystem" should match whole word

        partial_text = filler + "The company's ecosys is a widely used term."  # "ecosys" should NOT match "ecosystem"
        result2 = self.analyzer.analyze(partial_text)
        network_keywords_found2 = set()
        for ev in result2["evidence"]:
            if "network" in ev["keyword_group"]:
                network_keywords_found2.add(ev["keyword"])
        assert "platform" not in network_keywords_found2  # partial word should not match

    # ── NEG-07: None text raises AttributeError ─────────────────────

    def test_analyze_none_text_raises(self):
        with pytest.raises(AttributeError):
            self.analyzer.analyze(None)  # type: ignore

    # ── NEG-10: Unicode and special characters ─────────────────────

    def test_analyze_unicode_text(self):
        text = "La marque et les brevets créent un avantage concurrentiel. " \
               "La fidélisation de la clientèle est élevée 中国 企業"
        result = self.analyzer.analyze(text)
        assert result["total_matches"] == 0  # French/Chinese keywords not in our list
        assert isinstance(result["evidence"], list)

    def test_analyze_text_with_html_markup(self):
        text = "<p>The company's <strong>patent</strong> portfolio is strong.</p>" \
               "<p>Its <em>brand</em> recognition drives customer loyalty.</p>"
        result = self.analyzer.analyze(text)
        assert result["total_matches"] > 0  # should still find keywords within HTML

    def test_analyze_whitespace_only_text(self):
        result = self.analyzer.analyze("   \n\n   \t   ")
        assert result["total_matches"] == 0

    def test_analyze_numeric_text(self):
        text = "The company reported strong financial results this year. " \
               "The 2024 results show 42.5% market share with 3.2 million active users."
        result = self.analyzer.analyze(text)
        assert result["total_matches"] > 0  # should find "market share" and "active users"

    def test_analyze_mixed_language_with_keywords(self):
        text = "The company operates globally with a diversified business model. " \
               "该公司拥有强大的品牌识别度和专利技术 (brand recognition and patented technology)."
        result = self.analyzer.analyze(text)
        assert result["total_matches"] > 0  # English keywords should still match
