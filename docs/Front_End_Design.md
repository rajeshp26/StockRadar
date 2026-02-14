

web/
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
│   │   ├── auth/
│   │   │   ├── login-form.tsx
│   │   │   └── signup-form.tsx
│   │   ├── dashboard/
│   │   │   ├── add-stock-dialog.tsx
│   │   │   ├── stock-card.tsx
│   │   │   └── watchlist.tsx
│   │   ├── FirebaseErrorListener.tsx
│   │   ├── header.tsx
│   │   ├── icons.tsx
│   │   └── ui/
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
│   │   │   │   ├── intrinsic-panel.tsx
│   │   │   │   ├── intrinsic-value-root.tsx
│   │   │   │   ├── method-panel.tsx
│   │   │   │   ├── rule1-panel.tsx
│   │   │   │   ├── shared.tsx
│   │   │   │   └── valuation-overview.tsx
│   │   │   ├── hooks/
│   │   │   │   ├── useAnalysis.ts
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
