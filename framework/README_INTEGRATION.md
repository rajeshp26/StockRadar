# Agentic Framework Integration

This framework now includes clean architectural patterns from the Lanham/Gulli educational frameworks integrated alongside the existing production enforcement system.

## New Components

- skill_contracts/ - Clean SkillSpec, ToolSpec, RunContext contracts
- gateways/ - Explicit gateway abstractions
- patterns/ - Reusable patterns
- loops/ - Loop implementations
- mcp/ - MCP registry and config generation
- adapters/ - Bridging layer between clean patterns and enforcement
- llm.py, context.py, tracing.py - Supporting utilities

All existing gates and enforcement mechanisms remain unchanged.
