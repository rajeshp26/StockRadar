# Production-grade integrations configuration
# All integrations are opt-in by default

integrations:
  opencode:
    keepalive:
      # Enable OpenCode keep-alive to prevent 60-minute session interruptions
      # This is opt-in and requires explicit enablement
      enabled: false
      # Refresh interval in seconds (must be < 3600, recommended 2700 = 45 min)
      interval_seconds: 2700
      # Locations to keep fresh (empty = current working directory)
      locations: []
      # Path to OpenCode CLI (empty = auto-detect)
      cli_path: ""
