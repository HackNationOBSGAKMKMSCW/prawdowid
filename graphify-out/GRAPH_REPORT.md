# Graph Report - prawdowid-apiReading  (2026-11-21)

## Corpus Check
- 12 files · ~9,451 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 385 nodes · 691 edges · 34 communities (17 shown, 17 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 36 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Concurrent Fetch Aggregation
- Base API Client Lifecycle
- Google Fact Check Integration
- Frontend API Integration
- Reading Request Validation
- Frontend Package Dependencies
- Category-Driven Reader Docs
- Async API Layer Plan
- Frontend TypeScript App Config
- Google Request Construction
- Frontend Node Configuration
- FastAPI Item Routes
- Prettier Configuration
- Vercel Deployment Configuration
- Frontend Tooling Overview
- Oxlint Configuration
- Frontend HTML Entry
- TypeScript Project References
- API Reading Documentation Concepts
- FastAPI Framework Dependency
- Uvicorn Server Dependency
- Favicon Illustration
- Bluesky Icon
- Discord Icon
- Documentation Icon
- GitHub Icon
- Social Profile Icon
- SVG Icon Sprite
- X Social Network Icon
- Hero Stack Illustration
- React Logo Asset
- Vite Logo Asset

## God Nodes (most connected - your core abstractions)
1. `BaseApiClient` - 42 edges
2. `ReadingRequest` - 25 edges
3. `read()` - 22 edges
4. `GoogleFactCheckClient` - 21 edges
5. `ApiReadingError` - 19 edges
6. `compilerOptions` - 18 edges
7. `InvalidFiltersError` - 18 edges
8. `FetchResult` - 16 edges
9. `compilerOptions` - 15 edges
10. `RequestSpec` - 15 edges

## Surprising Connections (you probably didn't know these)
- `ReadingRequest` --semantically_similar_to--> `ReadingRequest`  [INFERRED] [semantically similar]
  backend/dataPreparation/apiReading/README.md → docs/plans/2026-11-21-002-feat-category-driven-async-reader-plan.md
- `ReadingResult` --semantically_similar_to--> `ReadingResult`  [INFERRED] [semantically similar]
  backend/dataPreparation/apiReading/README.md → docs/plans/2026-11-21-002-feat-category-driven-async-reader-plan.md
- `httpx Dependency` --references--> `BaseApiClient Abstract Base Class`  [EXTRACTED]
  backend/requirements.txt → docs/plans/2026-11-21-001-feat-async-multi-api-fetcher-layer-plan.md
- `read()` --conceptually_related_to--> `read() Orchestration`  [INFERRED]
  backend/dataPreparation/apiReading/README.md → docs/plans/2026-11-21-002-feat-category-driven-async-reader-plan.md
- `fetch_all()` --uses--> `BaseApiClient`  [INFERRED]
  backend/dataPreparation/apiReading/aggregator.py → backend/dataPreparation/apiReading/base.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Async Multi-API Fetcher Architecture** — docs_plans_2026_11_21_001_feat_async_multi_api_fetcher_layer_plan_baseapiclient, docs_plans_2026_11_21_001_feat_async_multi_api_fetcher_layer_plan_concrete_api_clients, docs_plans_2026_11_21_001_feat_async_multi_api_fetcher_layer_plan_fetch_all_aggregator, docs_plans_2026_11_21_001_feat_async_multi_api_fetcher_layer_plan_fetchresult, docs_plans_2026_11_21_001_feat_async_multi_api_fetcher_layer_plan_fetchoutcome [EXTRACTED 1.00]
- **Reusable SVG symbol sprite contents** — frontend_public_icons_svg_icon_sprite, frontend_public_icons_bluesky_icon, frontend_public_icons_discord_icon, frontend_public_icons_documentation_icon, frontend_public_icons_github_icon, frontend_public_icons_social_icon, frontend_public_icons_x_icon [EXTRACTED 1.00]

## Communities (34 total, 17 thin omitted)

### Community 0 - "Concurrent Fetch Aggregation"
Cohesion: 0.08
Nodes (10): fetch_all(), ApiConnectionError, ApiReadingError, ApiResponseError, ApiTimeoutError, NoSourcesAvailableError, Category, FetchOutcome (+2 more)

### Community 1 - "Base API Client Lifecycle"
Cohesion: 0.07
Nodes (8): BaseApiClient, _parse_retry_after(), ApiAuthError, ApiHttpError, ApiRateLimitError, FetchResult, test_base_client_is_abstract_and_clients_share_fetch_signature(), _OtherClient

### Community 2 - "Google Fact Check Integration"
Cohesion: 0.10
Nodes (19): GoogleFactCheckClient, Item, test_client_requires_https_base_url(), test_fetch_all_can_propagate_errors(), test_fetch_all_runs_concurrently_and_keeps_other_success_on_failure(), test_fetch_maps_response_and_preserves_raw_payload(), test_google_fact_check_paginates_with_opaque_cursor(), test_google_fact_check_rejects_invalid_filters_without_request() (+11 more)

### Community 3 - "Frontend API Integration"
Cohesion: 0.15
Nodes (15): dependencies, react@^19.3.1, react-dom@^19.3.1, react-router-dom@^7.18.6, api, Item, App(), About() (+7 more)

### Community 4 - "Reading Request Validation"
Cohesion: 0.14
Nodes (10): ReadingRequest, read(), test_invalid_requests_raise_typed_error_before_http(), test_owned_http_client_closes_when_read_is_cancelled(), create_client(), test_read_fans_out_once_per_client_and_aggregates_partial_failure(), handler(), test_read_missing_key_returns_auth_outcome_without_request() (+2 more)

### Community 5 - "Frontend Package Dependencies"
Cohesion: 0.10
Nodes (24): devDependencies, oxlint@^1.90.0, @types/node@^24.19.2, @types/react@^19.3.0, @types/react-dom@^19.3.0, typescript@~7.0.2, vite@^8.3.6, @vitejs/plugin-react@^6.1.2 (+16 more)

### Community 6 - "Category-Driven Reader Docs"
Cohesion: 0.09
Nodes (17): Category.FACT_CHECK, Google Fact Check Tools API, httpx.AsyncClient, NoSourcesAvailableError, read(), ReadingRequest, ReadingResult, BaseApiClient (+9 more)

### Community 7 - "Async API Layer Plan"
Cohesion: 0.10
Nodes (18): httpx Dependency, Pydantic v2 Dependency, pytest Dependency, pytest-asyncio Dependency, respx Dependency, Concurrent Multi-API Fetching, API-Specific Filter Validation, Typed ApiReadingError Hierarchy (+10 more)

### Community 8 - "Frontend TypeScript App Config"
Cohesion: 0.10
Nodes (19): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+11 more)

### Community 9 - "Google Request Construction"
Cohesion: 0.16
Nodes (5): RequestSpec, _claim_id(), _optional_nonempty_string(), InvalidFiltersError, fetch_with()

### Community 10 - "Frontend Node Configuration"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 11 - "FastAPI Item Routes"
Cohesion: 0.23
Nodes (8): create_item(), delete_item(), get_item(), health(), Item, ItemCreate, list_items(), test()

### Community 12 - "Prettier Configuration"
Cohesion: 0.15
Nodes (12): arrowParens, bracketSameLine, bracketSpacing, endOfLine, jsxSingleQuote, printWidth, $schema, semi (+4 more)

### Community 13 - "Vercel Deployment Configuration"
Cohesion: 0.22
Nodes (8): entrypoint, root, framework, root, rewrites, services, backend, frontend

### Community 14 - "Frontend Tooling Overview"
Cohesion: 0.25
Nodes (7): Hot Module Replacement, Oxlint Rules, oxlint-tsgolint, React TypeScript Vite Template, @vitejs/plugin-react using Oxc, @vitejs/plugin-react-swc using SWC, Type-Aware Oxlint Configuration

### Community 15 - "Oxlint Configuration"
Cohesion: 0.33
Nodes (5): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 16 - "Frontend HTML Entry"
Cohesion: 0.40
Nodes (5): SVG Favicon, Frontend Page Title, Frontend HTML Document, src/main.tsx Entry Module, React Root Mount Element

## Knowledge Gaps
- **39 isolated node(s):** `Hot Module Replacement`, `oxlint-tsgolint`, `@vitejs/plugin-react using Oxc`, `@vitejs/plugin-react-swc using SWC`, `SVG Favicon` (+34 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 181 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BaseApiClient` connect `Base API Client Lifecycle` to `Concurrent Fetch Aggregation`, `Google Request Construction`, `Google Fact Check Integration`, `Reading Request Validation`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `BaseApiClient` (e.g. with `fetch_all()` and `ApiAuthError`) actually correct?**
  _`BaseApiClient` has 14 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Hot Module Replacement`, `oxlint-tsgolint`, `@vitejs/plugin-react using Oxc` to the rest of the system?**
  _39 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Concurrent Fetch Aggregation` be split into smaller, more focused modules?**
  _Cohesion score 0.08408163265306122 - nodes in this community are weakly interconnected._
- **Why does `ReadingRequest` connect `Reading Request Validation` to `Concurrent Fetch Aggregation`, `Base API Client Lifecycle`, `Google Fact Check Integration`, `Google Request Construction`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `ReadingRequest` (e.g. with `BaseApiClient` and `GoogleFactCheckClient`) actually correct?**
  _`ReadingRequest` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `Base API Client Lifecycle` be split into smaller, more focused modules?**
  _Cohesion score 0.06859903381642513 - nodes in this community are weakly interconnected._