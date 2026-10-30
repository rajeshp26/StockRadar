status: approved
title: Correct the dividend sector chart colour mapping
files_or_components:
  - web/src/features/portfolio/components/DividendSectorChart.tsx
acceptance_criteria:
  - AC-1 [unit] sector_colour returns the token name for every declared sector and never an empty string
  - AC-2 [integration] the chart renders one segment per sector and the legend order matches the series order
  - AC-3 [browser] in the portfolio tab the donut shows every sector in its own colour and a hovered segment raises its label, driven by real portfolio data with no mocks
discovery:
  - code [VERIFIED: web/src/features/portfolio/components/DividendSectorChart.tsx:1-40] the chart builds segment colours inline from a local map
  - architecture [VERIFIED: web/src/features/portfolio/hooks/usePortfolio.ts:1-40] the chart consumes the portfolio hook, not a direct service call
  - design [VERIFIED: framework/opencode/skills/apple-ui/SKILL.md:1-20] the dashboard palette and glass depth rules live in the design system skill
  - environment [VERIFIED: python3 --version] interpreter and flags confirmed in this run
  - data [NA: the sector list is static, no dataset involved]
reuse:
  - sector colour map -> web/src/features/portfolio/components/DividendSectorChart.tsx
required_skills:
  - frontend-react
  - unit-test-authoring
