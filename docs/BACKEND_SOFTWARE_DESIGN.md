
# Backend Software Design Document

This document provides a detailed overview of the backend software design for StockerPro, intended to help new developers quickly understand the codebase, architecture, and key components.

## 1. High-Level Architecture

The backend follows a layered architecture pattern, promoting separation of concerns and modularity. This makes the system easier to maintain, test, and scale. The layers are:

- **API Layer (Presentation):** Handles incoming HTTP requests, performs data validation, and calls the appropriate services. It's built with FastAPI.
- **Application Layer (Service):** Contains the core business logic. It orchestrates calls to the domain and infrastructure layers to fulfill use cases.
- **Domain Layer:** Represents the core business concepts, entities, and rules of the application. It is independent of any specific framework or technology.
- **Infrastructure Layer:** Implements interfaces defined in the domain layer, handling external concerns like database interactions and communication with third-party services.
- **Providers Layer:** A specific part of the infrastructure layer responsible for fetching data from external sources (e.g., stock price data).

## 2. Folder Structure and File Descriptions

Here’s a breakdown of the key files and their responsibilities within the `backend/` directory:

```
backend/
├── api/
│   ├── users.py
│   ├── watchlist_items.py
│   └── watchlists.py
├── application/
│   └── services/
│       └── watchlist_service.py
├── domain/
│   ├── entities/
│   │   └── watchlist.py
│   └── interfaces/
│       ├── repository.py
│       └── stock_provider.py
├── infrastructure/
│   └── repositories/
│       └── supabase_repository.py
├── providers/
│   └── yfinance_provider.py
├── main.py
├── auth.py
├── config.py
├── database.py
└── dependencies.py
```

### 2.1. `main.py`

- **Purpose:** The main entry point of the FastAPI application.
- **Key Responsibilities:**
    - Initializes the FastAPI app.
    - Configures CORS middleware, rate limiting, and exception handlers.
    - Includes the API routers (`users`, `watchlists`, `watchlist_items`).
    - Defines system-level endpoints like `/health` and `/ready`.
    - Manages the application's startup and shutdown events (lifespan), including initializing Firebase and starting a background task for stock price monitoring.

### 2.2. API Layer (`api/`)

- **`users.py`:** Manages user-related endpoints.
    - **`POST /users/sync`:** Synchronizes user data from Firebase Auth to the Supabase database. It performs an "upsert" operation to create or update a user profile.
- **`watchlists.py`:** Handles watchlist-specific endpoints.
    - **`POST /watchlists/default-with-items`:** Retrieves the default watchlist for a user, including all the stocks within it and their current market data.
    - **`GET /watchlists/stream`:** Establishes a Server-Sent Events (SSE) connection to stream real-time stock price updates to the client.
- **`watchlist_items.py`:** Manages the items (stocks) within a watchlist.
    - **`POST /watchlist-items`:** Adds a new stock to a watchlist.
    - **`PATCH /watchlist-items/{item_id}`:** Updates the target buy/sell prices for a watchlist item.
    - **`POST /watchlist-items/delete`:** Removes a stock from a watchlist.

### 2.3. Application Layer (`application/`)

- **`services/watchlist_service.py`:** Contains the business logic for watchlist operations.
    - **`get_default_watchlist_with_items`:** Orchestrates the process of fetching a user's default watchlist, its items, and the latest stock data by coordinating with the user repository, watchlist repository, and stock provider.

### 2.4. Domain Layer (`domain/`)

- **`entities/watchlist.py`:** Defines the core data structures (Pydantic models) of the application, such as `WatchlistWithStocks` and `StockPriceInfo`. These models represent the business objects and are used for data validation and serialization.
- **`interfaces/repository.py`:** Defines the abstract base classes (interfaces) for the data repositories (`WatchlistRepository`, `UserRepository`). This decouples the application logic from the specific database implementation.
- **`interfaces/stock_provider.py`:** Defines the interface for a stock data provider, ensuring that the application can easily switch between different data sources.

### 2.5. Infrastructure Layer (`infrastructure/`)

- **`repositories/supabase_repository.py`:** Implements the repository interfaces defined in the domain layer using Supabase as the backend. It handles all direct database interactions.
- **`providers/yfinance_provider.py`:** Implements the `StockProvider` interface using the `yfinance` library to fetch stock data from Yahoo Finance.

## 3. Class Diagrams (Text-Based)

### 3.1. Watchlist Service and Dependencies

This diagram shows how the `WatchlistService` interacts with its dependencies to retrieve watchlist data.

```
[FastAPI Router] -> [WatchlistService]
      |                   |
      |                   v
      |            [UserRepository (Interface)]
      |                   ^
      |                   |
      |            [SupabaseUserRepository]
      |
      |                   v
      |            [WatchlistRepository (Interface)]
      |                   ^
      |                   |
      |            [SupabaseWatchlistRepository]
      |
      |                   v
      +----------> [StockProvider (Interface)]
                          ^
                          |
                   [YFinanceProvider]
```

### 3.2. Data Flow for Adding a Stock

This illustrates the sequence of operations when a user adds a stock to their watchlist.

```
Client (POST /watchlist-items)
     |
     v
[API Layer: watchlist_items.py]
 - Validates request data (WatchlistItemIn)
 - Checks user authentication
     |
     v
[YFinanceProvider] - Fetches stock details from Yahoo Finance
     |
     v
[Infrastructure Layer: supabase_repository.py]
 - Upserts company information into the `companies` table
 - Upserts market data into the `current_market_data` table
 - Inserts the new item into the `watchlist_items` table
     |
     v
[BackgroundTasks] - Triggers a background task to sync additional company data
     |
     v
Client (Receives 201 Created with stock data)
```

## 4. Key Concepts and Logic

- **Authentication:** User authentication is handled via Firebase Authentication. A JWT token is sent in the `Authorization` header of each request. The `auth.py` and `dependencies.py` files contain the logic to verify these tokens and retrieve the current user.
- **Real-time Updates:** The application uses Server-Sent Events (SSE) to push real-time stock price updates to connected clients. The `main.py` file runs a background task that continuously monitors stock prices for symbols in active watchlists and broadcasts updates.
- **Database:** Supabase (a PostgreSQL-based platform) is used as the primary database. The `database.py` file initializes the Supabase client.
- **Dependency Injection:** FastAPI's dependency injection system is used to provide services, repositories, and the current user to the API endpoints. This promotes loose coupling and makes testing easier.
- **Configuration:** Application settings are managed in `config.py`, which loads environment variables for different environments (e.g., development, production).

## 5. Real-Time Data Flow and `yfinance` Integration

This section details how the application retrieves real-time and other stock information from Yahoo Finance using the `yfinance` library.

### 5.1. Initialization and Core Components

- **`YFinanceProvider` (`providers/yfinance_provider.py`):** This class is the concrete implementation of the `StockProvider` interface. It is responsible for all interactions with the `yfinance` library. The `YFinanceProvider` is initialized as a singleton within the application's dependency injection system, ensuring that a single instance is shared across the application.
- **Background Price Monitor (`main.py`):** A background task (`background_price_monitor`) is started when the FastAPI application launches. This task is responsible for periodically fetching and broadcasting stock price updates.

### 5.2. `yfinance` APIs in Use

The application primarily uses two features of the `yfinance` library:

1.  **`yf.Ticker(ticker_symbol)`:** This function is used to get a `Ticker` object for a single stock symbol. We then access the `.info` attribute on this object. The `.info` attribute returns a Python dictionary containing a comprehensive set of details about the stock, including current price, previous close, company name, exchange, and much more. This is used in the `get_stock_details` method of the `YFinanceProvider` when a user adds a new stock to their watchlist to get all the initial data.

2.  **`yf.Tickers(ticker_symbols)`:** This function is a more efficient way to fetch data for multiple tickers at once. It takes a list of ticker symbols and returns a dictionary of `Ticker` objects, where the keys are the ticker symbols. This is used in the `background_price_monitor` task to fetch updates for all stocks in active watchlists in a single batch request, which is much more efficient than making individual requests for each ticker.

### 5.3. Detailed Data Retrieval Flows

**A. Real-Time Price Updates (SSE):**

1.  **Client Connection:** A client establishes a connection to the `/watchlists/stream` SSE endpoint.
2.  **Background Task:** The `background_price_monitor` task in `main.py` runs in a continuous loop, waking up every 10 seconds.
3.  **Symbol Aggregation:** The task gathers a unique set of all stock symbols that are currently being watched by active clients connected to the SSE stream.
4.  **Batch Data Fetch:** It makes a single batch call using `yf.Tickers(list_of_symbols)`. This is the most critical part of the real-time update flow. 
5.  **Data Extraction:** For each symbol in the response, it extracts the relevant price information from the `.info` dictionary of the corresponding `Ticker` object. Specifically, it looks for the following fields in order of preference: `'currentPrice'`, `'regularMarketPrice'`, and `'regularMarketPreviousClose'`. This provides a fallback mechanism in case one of the price fields is not available.
6.  **Change Calculation:** The price change and percentage change are calculated by comparing the current price to the `'regularMarketPreviousClose'` value.
7.  **Broadcasting:** The newly retrieved and calculated price data for each symbol is then broadcast as a Server-Sent Event to all relevant clients subscribed to that symbol.

**B. Adding a New Stock to a Watchlist:**

1.  **API Request:** A user makes a `POST` request to the `/watchlist-items` endpoint with a new stock symbol.
2.  **Stock Details Fetch:** The endpoint calls the `stock_provider.get_stock_details(symbol)` method.
3.  **`yfinance` Interaction:** Inside `get_stock_details` in the `yfinance_provider.py` file, the `yf.Ticker(symbol)` function is called to get the `Ticker` object. The `.info` attribute is then accessed to retrieve all available information for that stock.
4.  **Database Population:** The detailed information, such as the company's long name, exchange, sector, industry, and a comprehensive set of market data points (open price, high, low, volume, etc.), is extracted from the `.info` dictionary. This information is then used to populate the `companies` and `current_market_data` tables in the Supabase database. This ensures that the application has a local cache of detailed stock information.

### 5.4. Impact Analysis for Future Modifications

Modifications to the `yfinance` integration are critical and can have a wide-ranging impact on the application. Any developer working on this part of the codebase should be aware of the following:

- **Changing Data Points:** If you need to extract new or different data points from the `yfinance` `.info` dictionary (e.g., 52-week high, dividend yield), you will need to:
    - Update the `StockDetails` model in `providers/base.py` to include the new fields.
    - Potentially modify the database schema of the `companies` or `current_market_data` tables to store this new information.
    - Update the data extraction logic in `yfinance_provider.py` to retrieve the new fields from the `.info` dictionary.

- **Modifying Price Logic:** The `get_stock_details` method contains fallback logic for determining the current price. Any changes to this logic will directly impact the price displayed to all users and the data stored in the database. These changes must be thoroughly tested to ensure accuracy and prevent unintended side effects.

- **Adjusting the SSE Update Frequency:** The `background_price_monitor` in `main.py` is configured with a 10-second sleep interval (`asyncio.sleep(10)`). 
    - **Decreasing this interval** will provide more frequent, "more real-time" updates but will significantly increase the number of API requests to Yahoo Finance. This carries a high risk of the application's IP address being rate-limited or even temporarily blocked by Yahoo Finance.
    - **Increasing this interval** will reduce the load on both our application and the Yahoo Finance servers, but the data will become less "real-time" for the end-users. The current 10-second interval is a balance between these two concerns.

- **`yfinance` Library and API Changes:** The `yfinance` library is an unofficial wrapper around the Yahoo Finance API. This means it is susceptible to breaking changes if Yahoo Finance modifies its API structure. If data retrieval starts failing, it is likely that `yfinance` needs to be updated, or the data extraction logic in `yfinance_provider.py` needs to be adjusted to accommodate changes in the structure of the `.info` dictionary. Regular monitoring of the library's repository for updates and breaking changes is recommended.

- **Error and Exception Handling:** The `get_stock_details` method has a `try...except` block to gracefully handle errors from `yfinance` (e.g., for an invalid ticker symbol). If you are making modifications, it is crucial to maintain and, if necessary, enhance this error handling to prevent the entire application from crashing due to an issue with a single stock symbol retrieval. This is especially important in the `background_price_monitor` task, as a single failure should not stop the updates for all other stocks.

## 6. Code Comments and Further Exploration

While this document provides a high-level overview, the code itself is the ultimate source of truth. The code is generally well-structured and contains comments for complex logic. For a deeper understanding, it is recommended to:

- **Review the Pydantic models** in `domain/entities/` to understand the data structures.
- **Examine the service methods** in `application/services/` to see how business logic is implemented.
- **Trace the execution flow** of a request from the API layer down to the infrastructure layer.

This document should serve as a solid starting point for any new developer joining the StockerPro team.
