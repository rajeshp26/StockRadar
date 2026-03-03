.
├── .idx/
│   ├── dev.nix
│   └── icon.png
├── apphosting.yaml
├── backend/
│   ├── api/
│   │   ├── users.py
│   │   ├── valuations.py
│   │   ├── watchlist_items.py
│   │   └── watchlists.py
│   ├── application/
│   │   ├── jobs/
│   │   │   ├── data_quality_audit_job.py
│   │   │   └── derived_financial_metrics_job.py
│   │   ├── normalizers/
│   │   │   └── statement_normalizer.py
│   │   ├── schedulers/
│   │   │   ├── __init__.py
│   │   │   ├── earnings_scheduler.py
│   │   │   └── market_data_scheduler.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── dcf_service.py
│   │   │   ├── dcf_suitability.py
│   │   │   ├── ddm_service.py
│   │   │   ├── ddm_suitability.py
│   │   │   ├── recompute_guard.py
│   │   │   ├── rule1_suitability.py
│   │   │   ├── valuation_service.py
│   │   │   └── watchlist_service.py
│   │   └── __init__.py
│   ├── auth.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── __init__.py
│   │   │   └── watchlist.py
│   │   ├── exceptions.py
│   │   ├── __init__.py
│   │   ├── interfaces/
│   │   │   ├── __init__.py
│   │   │   ├── repository.py
│   │   │   └── stock_provider.py
│   │   ├── model_types.py
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── valuation_dcf.py
│   │       ├── valuation_ddm.py
│   │       └── valuation_rule1.py
│   ├── google_credentials.json
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── financial_repository.py
│   │       ├── supabase_repository.py
│   │       └── valuation_repository.py
│   ├── main.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── defeat_beta_provider.py
│   │   └── yfinance_provider.py
│   ├── requirements.txt
│   ├── schemas.py
│   ├── service-account.json
│   ├── services/
│   │   └── sync_service.py
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── exceptions/
│   │   │   ├── __init__.py
│   │   │   └── base.py
│   │   └── finance_math.py
│   ├── start-prod.sh
│   ├── start.sh
│   ├── status.sh
│   └── stop.sh
├── docs/
│   ├── AI_DEBUGGING_PROTOCOL.md
│   ├── ANALYSIS.md
│   ├── ARCHITECTURE.md
│   ├── Authentication_Refactor_Design.md
│   ├── BACKEND_SOFTWARE_DESIGN.md
│   ├── Backend_api_doc.md
│   ├── CHANGE_ANALYSIS_CHECKLIST.md
│   ├── DDM Design.md
│   ├── DESIGN_GUIDELINES.md
│   ├── DIAGNOSTICS_GUIDELINES.md
│   ├── ENVIRONMENT_SETUP_GUIDE.md
│   ├── FLUTTER_GUIDE.md
│   ├── Front_End_Design.md
│   ├── Login_Watchlist_Flow.md
│   ├── README.md
│   ├── SECURITY_GUIDELINES.md
│   ├── Supabase_Schema.md
│   ├── TESTING_GUIDE.md
│   ├── TROUBLESHOOTING_LOG.md
│   ├── VERIFIED_COMMANDS.md
│   ├── backend.json
│   ├── blueprint.md
│   ├── revert_plan.md
│   ├── sync_mapping_reference.md
│   └── test_deep_sync_guide.md
├── firebase.json
├── firestore.rules
├── mobile/
│   ├── README.md
│   ├── analysis_options.yaml
│   ├── lib/
│   │   ├── core/
│   │   │   ├── api/
│   │   │   │   ├── api_client.dart
│   │   │   │   ├── api_exception.dart
│   │   │   │   ├── api_exception.freezed.dart
│   │   │   │   ├── api_result.dart
│   │   │   │   ├── api_result.freezed.dart
│   │   │   │   └── auth_interceptor.dart
│   │   │   ├── config/
│   │   │   │   ├── environment.dart
│   │   │   │   └── firebase_config.dart
│   │   │   ├── models/
│   │   │   │   ├── watchlist.dart
│   │   │   │   ├── watchlist.freezed.dart
│   │   │   │   └── watchlist.g.dart
│   │   │   ├── providers/
│   │   │   │   ├── api_provider.dart
│   │   │   │   └── api_provider.g.dart
│   │   │   └── services/
│   │   │       └── watchlist_service.dart
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   │   └── providers/
│   │   │   │       ├── auth_provider.dart
│   │   │   │       └── auth_provider.g.dart
│   │   │   └── watchlist/
│   │   │       ├── presentation/
│   │   │       │   ├── screens/
│   │   │       │   │   └── watchlist_screen.dart
│   │   │       │   └── widgets/
│   │   │       │       └── stock_card.dart
│   │   │       └── providers/
│   │   │           ├── watchlist_provider.dart
│   │   │           └── watchlist_provider.g.dart
│   │   ├── main.dart
│   │   ├── preview_main.dart
│   │   └── shared/
│   │       └── widgets/
│   │           ├── glass_card.dart
│   │           └── watchlist_shimmer.dart
│   ├── manage.sh
│   ├── pubspec.lock
│   ├── pubspec.yaml
│   ├── test/
│   │   └── widget_test.dart
│   └── web/
│       ├── favicon.png
│       ├── icons/
│       │   ├── Icon-192.png
│       │   ├── Icon-512.png
│       │   ├── Icon-maskable-192.png
│       │   └── Icon-maskable-512.png
│       ├── index.html
│       └── manifest.json
├── package-lock.json
├── run.sh
├── scripts/
│   ├── debug_backend_sync.py
│   ├── debug_stock.py
│   ├── dev-setup.sh
│   ├── diagnostic.sh
│   └── generate_test_token.py
├── shell.nix
├── tests/
│   ├── README.md
│   ├── backend/
│   │   ├── test_deep_sync.py
│   │   ├── test_rule1_service.py
│   │   ├── test_watchlist_flow.py
│   │   └── test_watchlist_service_unit.py
│   └── e2e/
│       └── test_user_sync.py
└── web/
    ├── components.json
    ├── next-env.d.ts
    ├── next.config.js
    ├── package-lock.json
    ├── package.json
    ├── postcss.config.mjs
    ├── public/
    │   ├── icon-192.png
    │   └── manifest.json
    ├── src/
    │   ├── ai/
    │   │   ├── dev.ts
    │   │   └── genkit.ts
    │   ├── app/
    │   │   ├── (authenticated)/
    │   │   │   ├── analysis/
    │   │   │   │   └── [symbol]/
    │   │   │   │       └── page.tsx
    │   │   │   ├── dashboard/
    │   │   │   │   └── page.tsx
    │   │   │   ├── layout.tsx
    │   │   │   ├── profile/
    │   │   │   │   └── page.tsx
    │   │   │   ├── settings/
    │   │   │   │   └── page.tsx
    │   │   │   └── watchlist/
    │   │   │       └── page.tsx
    │   │   ├── api/
    │   │   │   ├── auth/
    │   │   │   │   └── session/
    │   │   │   │       └── route.ts
    │   │   │   └── proxy/
    │   │   │       └── [...path]/
    │   │   │           └── route.ts
    │   │   ├── favicon.ico
    │   │   ├── globals.css
    │   │   ├── layout.tsx
    │   │   ├── login/
    │   │   │   └── page.tsx
    │   │   ├── page.tsx
    │   │   └── signup/
    │   │       └── page.tsx
    │   ├── components/
    │   │   ├── FirebaseErrorListener.tsx
    │   │   ├── auth/
    │   │   │   ├── login-form.tsx
    │   │   │   └── signup-form.tsx
    │   │   ├── dashboard/
    │   │   │   ├── add-stock-dialog.tsx
    │   │   │   ├── stock-card.tsx
    │   │   │   ├── stock-list-row.tsx
    │   │   │   ├── watchlist-switcher.tsx
    │   │   │   ├── watchlist-toolbar.tsx
    │   │   │   └── watchlist.tsx
    │   │   ├── header.tsx
    │   │   ├── icons.tsx
    │   │   ├── ui/
    │   │   │   ├── accordion.tsx
    │   │   │   ├── alert-dialog.tsx
    │   │   │   ├── alert.tsx
    │   │   │   ├── avatar.tsx
    │   │   │   ├── badge.tsx
    │   │   │   ├── button.tsx
    │   │   │   ├── calendar.tsx
    │   │   │   ├── card.tsx
    │   │   │   ├── carousel.tsx
    │   │   │   ├── chart.tsx
    │   │   │   ├── checkbox.tsx
    │   │   │   ├── collapsible.tsx
    │   │   │   ├── dialog.tsx
    │   │   │   ├── dropdown-menu.tsx
    │   │   │   ├── form.tsx
    │   │   │   ├── input.tsx
    │   │   │   ├── label.tsx
    │   │   │   ├── menubar.tsx
    │   │   │   ├── popover.tsx
    │   │   │   ├── progress.tsx
    │   │   │   ├── radio-group.tsx
    │   │   │   ├── scroll-area.tsx
    │   │   │   ├── select.tsx
    │   │   │   ├── separator.tsx
    │   │   │   ├── sheet.tsx
    │   │   │   ├── sidebar.tsx
    │   │   │   ├── skeleton.tsx
    │   │   │   ├── slider.tsx
    │   │   │   ├── switch.tsx
    │   │   │   ├── table.tsx
    │   │   │   ├── tabs.tsx
    │   │   │   ├── textarea.tsx
    │   │   │   ├── toast.tsx
    │   │   │   ├── toaster.tsx
    │   │   │   └── tooltip.tsx
    │   │   └── user-nav.tsx
    │   ├── features/
    │   │   ├── analysis/
    │   │   │   ├── analytics/
    │   │   │   │   └── analysis.analytics.ts
    │   │   │   ├── components/
    │   │   │   │   ├── dcf-history.tsx
    │   │   │   │   ├── dcf-how.tsx
    │   │   │   │   ├── dcf-method.tsx
    │   │   │   │   ├── dcf-panel.tsx
    │   │   │   │   ├── dcf-suitability.tsx
    │   │   │   │   ├── dcf-summary.tsx
    │   │   │   │   ├── ddm-panel.tsx
    │   │   │   │   ├── intrinsic-panel.tsx
    │   │   │   │   ├── method-panel.tsx
    │   │   │   │   ├── method-selector.tsx
    │   │   │   │   ├── rule1-panel.tsx
    │   │   │   │   ├── shared-ui.tsx
    │   │   │   │   └── valuation-overview.tsx
    │   │   │   ├── hooks/
    │   │   │   │   ├── useAnalysis.ts
    │   │   │   │   ├── useDcfAnalysis.ts
    │   │   │   │   ├── useDcfHistory.ts
    │   │   │   │   ├── useDdmAnalysis.ts
    │   │   │   │   ├── useDdmHistory.ts
    │   │   │   │   ├── useLivePrice.ts
    │   │   │   │   └── useRule1History.ts
    │   │   │   ├── services/
    │   │   │   │   └── analysis.service.ts
    │   │   │   ├── types/
    │   │   │   │   └── analysis.types.ts
    │   │   │   └── valuation/
    │   │   │       └── methods.ts
    │   │   ├── auth/
    │   │   │   ├── services/
    │   │   │   │   ├── auth.service.ts
    │   │   │   │   └── token-manager.ts
    │   │   │   └── types/
    │   │   │       └── auth.types.ts
    │   │   └── watchlists/
    │   │       ├── hooks/
    │   │       │   └── useWatchlist.ts
    │   │       ├── services/
    │   │       │   └── watchlist.service.ts
    │   │       └── types/
    │   │           └── watchlist.types.ts
    │   ├── firebase/
    │   │   ├── client-provider.tsx
    │   │   ├── config.ts
    │   │   ├── error-emitter.ts
    │   │   ├── errors.ts
    │   │   ├── firestore/
    │   │   │   ├── use-collection.tsx
    │   │   │   └── use-doc.tsx
    │   │   ├── index.ts
    │   │   ├── non-blocking-login.tsx
    │   │   ├── non-blocking-updates.tsx
    │   │   └── provider.tsx
    │   ├── hooks/
    │   │   ├── use-mobile.tsx
    │   │   ├── use-toast.ts
    │   │   └── useWatchlist.ts
    │   ├── lib/
    │   │   ├── api.ts
    │   │   ├── data.ts
    │   │   ├── performance.ts
    │   │   ├── placeholder-images.json
    │   │   ├── placeholder-images.ts
    │   │   ├── types.ts
    │   │   └── utils.ts
    │   ├── providers/
    │   │   └── auth-provider.tsx
    │   ├── proxy.ts
    │   ├── services/
    │   │   └── watchlist.service.ts
    │   └── shared/
    │       ├── constants.ts
    │       └── contexts/
    │           └── ServiceContext.tsx
    ├── tailwind.config.ts
    └── tsconfig.json
