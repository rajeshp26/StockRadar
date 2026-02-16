

web
├─ components.json
├─ next-env.d.ts
├─ next.config.js
├─ package-lock.json
├─ package.json
├─ postcss.config.mjs
├─ tailwind.config.ts
├─ tsconfig.json
├─ public
│  ├─ icon-192.png
│  └─ manifest.json
└─ src
   ├─ proxy.ts
   ├─ ai
   │  ├─ dev.ts
   │  └─ genkit.ts
   ├─ app
   │  ├─ favicon.ico
   │  ├─ globals.css
   │  ├─ layout.tsx
   │  ├─ page.tsx
   │  ├─ login
   │  │  └─ page.tsx
   │  ├─ signup
   │  │  └─ page.tsx
   │  ├─ (authenticated)
   │  │  ├─ layout.tsx
   │  │  ├─ dashboard
   │  │  │  └─ page.tsx
   │  │  ├─ profile
   │  │  │  └─ page.tsx
   │  │  ├─ settings
   │  │  │  └─ page.tsx
   │  │  ├─ watchlist
   │  │  │  └─ page.tsx
   │  │  └─ analysis
   │  │     └─ [symbol]
   │  │        └─ page.tsx
   │  └─ api
   │     ├─ auth
   │     │  └─ session
   │     │     └─ route.ts
   │     └─ proxy
   │        └─ [...path]
   │           └─ route.ts
   ├─ components
   │  ├─ FirebaseErrorListener.tsx
   │  ├─ header.tsx
   │  ├─ icons.tsx
   │  ├─ user-nav.tsx
   │  ├─ auth
   │  │  ├─ login-form.tsx
   │  │  └─ signup-form.tsx
   │  ├─ dashboard
   │  │  ├─ add-stock-dialog.tsx
   │  │  ├─ stock-card.tsx
   │  │  └─ watchlist.tsx
   │  └─ ui
   │     ├─ accordion.tsx
   │     ├─ alert-dialog.tsx
   │     ├─ alert.tsx
   │     ├─ avatar.tsx
   │     ├─ badge.tsx
   │     ├─ button.tsx
   │     ├─ calendar.tsx
   │     ├─ card.tsx
   │     ├─ carousel.tsx
   │     ├─ chart.tsx
   │     ├─ checkbox.tsx
   │     ├─ collapsible.tsx
   │     ├─ dialog.tsx
   │     ├─ dropdown-menu.tsx
   │     ├─ form.tsx
   │     ├─ input.tsx
   │     ├─ label.tsx
   │     ├─ menubar.tsx
   │     ├─ popover.tsx
   │     ├─ progress.tsx
   │     ├─ radio-group.tsx
   │     ├─ scroll-area.tsx
   │     ├─ select.tsx
   │     ├─ separator.tsx
   │     ├─ sheet.tsx
   │     ├─ sidebar.tsx
   │     ├─ skeleton.tsx
   │     ├─ slider.tsx
   │     ├─ switch.tsx
   │     ├─ table.tsx
   │     ├─ tabs.tsx
   │     ├─ textarea.tsx
   │     ├─ toast.tsx
   │     ├─ toaster.tsx
   │     └─ tooltip.tsx
   ├─ firebase
   │  ├─ client-provider.tsx
   │  ├─ config.ts
   │  ├─ error-emitter.ts
   │  ├─ errors.ts
   │  ├─ index.ts
   │  ├─ non-blocking-login.tsx
   │  ├─ non-blocking-updates.tsx
   │  ├─ provider.tsx
   │  └─ firestore
   │     ├─ use-collection.tsx
   │     └─ use-doc.tsx
   ├─ hooks
   │  ├─ use-mobile.tsx
   │  ├─ use-toast.ts
   │  └─ useWatchlist.ts
   ├─ lib
   │  ├─ api.ts
   │  ├─ data.ts
   │  ├─ performance.ts
   │  ├─ placeholder-images.json
   │  ├─ placeholder-images.ts
   │  ├─ types.ts
   │  └─ utils.ts
   ├─ providers
   │  └─ auth-provider.tsx
   ├─ services
   │  └─ watchlist.service.ts
   ├─ shared
   │  ├─ constants.ts
   │  └─ contexts
   │     └─ ServiceContext.tsx
   └─ features
      ├─ analysis
      │  ├─ analytics
      │  │  └─ analysis.analytics.ts
      │  ├─ components
      │  │  ├─ ddm-panel.tsx
      │  │  ├─ intrinsic-panel.tsx
      │  │  ├─ intrinsic-value-root.tsx
      │  │  ├─ method-panel.tsx
      │  │  ├─ method-selector.tsx
      │  │  ├─ rule1-panel.tsx
      │  │  ├─ shared-ui.tsx
      │  │  ├─ shared.tsx
      │  │  └─ valuation-overview.tsx
      │  ├─ hooks
      │  │  ├─ useAnalysis.ts
      │  │  ├─ useDdmAnalysis.ts
      │  │  ├─ useDdmHistory.ts
      │  │  ├─ useLivePrice.ts
      │  │  └─ useRule1History.ts
      │  ├─ services
      │  │  └─ analysis.service.ts
      │  ├─ types
      │  │  └─ analysis.types.ts
      │  └─ valuation
      │     └─ methods.ts
      ├─ auth
      │  ├─ services
      │  │  ├─ auth.service.ts
      │  │  └─ token-manager.ts
      │  └─ types
      │     └─ auth.types.ts
      └─ watchlists
         ├─ hooks
         │  └─ useWatchlist.ts
         ├─ services
         │  └─ watchlist.service.ts
         └─ types
            └─ watchlist.types.ts
