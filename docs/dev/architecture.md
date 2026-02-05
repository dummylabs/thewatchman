# Architecture & Design Principles
This document provides a high-level overview of the Watchman integration architecture. It is intended for new contributors or developers wishing to understand the internal logic, design choices, and data flow of the application.
## 1. High-Level Overview
Watchman is a custom integration for Home Assistant designed to audit configuration files. Its primary goal is to identify "orphan" entities—entity IDs referenced in your YAML configuration, dashboards, or automations that no longer exist in the Home Assistant state machine.

The system operates on a Scan → Analyze → Report cycle, optimized to minimize disk I/O and processing overhead.
## 2. Core Design Decisions
### 2.1. Naive Parsing Strategy (Regex vs. YAML)
One of the most critical architectural decisions in Watchman is the conscious choice to avoid a formal YAML parser.

**The Approach**: 
Configuration files are treated as raw text streams. We parse files line-by-line using Regular Expressions to identify patterns that look like entity IDs (e.g., domain.object_id).

**The Rationale**:
 * erformance: Regex processing is significantly faster than building a DOM for massive YAML files.
 * Robustness: Home Assistant configurations often contain custom tags (e.g., !include, !secret) or Jinja2 templates that standard YAML parsers fail to process without the full HA context.
 * Fault Tolerance: A syntax error in a user's YAML file will crash a formal parser. The regex approach simply skips the problematic line and continues scanning, ensuring the auditor remains operational even during configuration debugging.
### 2.2. Lifecycle & Caching (The "Snapshot" Model)
To ensure the integration does not degrade Home Assistant's performance, file parsing is **not real-time**.
1. **Startup Parsing**: Upon integration initialization, Watchman performs a "deep scan." It traverses the user's configuration directory, parses relevant files, and builds a global set of referenced entities.
2. **In-Memory Storage**: This list is stored in memory. When a user runs a check command, Watchman compares the current Home Assistant State Machine against this pre-calculated list.
3. **Benefit**: This decouples the heavy I/O operation (reading files) from the logic operation (checking states), making the actual "check" command instantaneous.
### 2.3. Event-Driven re-parsing
While the configuration is cached, it must not become stale. Watchman subscribes to specific Home Assistant events to trigger an automatic re-scan:
* `call_service` events: specifically `homeassistant.reload_core_config`, `automation.reload`, etc.
* **File System events**: (Where supported) changes to the `configuration.yaml` or valid sub-directories.

When these events are detected, the cached list of referenced entities is discarded and rebuilt in the background.
## 3. Data Flow
The following diagram illustrates the flow of data from the file system to the final report.

```
graph TD
    A[Home Assistant Startup] --> B{Watchman Init}
    B --> C[File System Walker]
    
    subgraph "Parser Engine"
        C --> D[Read File Line-by-Line]
        D --> E{Regex Match?}
        E -- Yes --> F[Extract Entity ID]
        E -- No --> D
    end
    
    F --> G[In-Memory Cache\n(Referenced Entities)]
    
    H[User Trigger / Automation] --> I[service: watchman.report]
    I --> J{Compare Cache vs.\nHA State Machine}
    
    J -- Entity Missing --> K[Add to Report]
    J -- Entity Exists --> L[Ignore]
    
    K --> M[Send Notification / Create File]
```

## 4. Key Components
### The Coordinator
Acts as the central brain. It holds the reference to the Hass object, manages the configuration options (defined in config_flow.py), and orchestrates the parsing jobs.
### The Parser (parser.py)
This module contains the regex logic. It is responsible for:
 * Recursively walking directories.
 * Respecting internal ignore lists.
 * Applying the regex patterns to extract domain.entity strings.
### The Reporter
Responsible for formatting the output. Watchman supports multiple output formats:
 * Text file: A generated report saved to the config folder.
 * Notification: Sending the results via a notification service (e.g., mobile app, email).
 The reporter can be extended for additional format e.g. HTML, CSV, etc, see `table_renderer` and `text_renderer` in the `report.py`.
## 5. Project Structure

```
[Project Root]/
├── docs/                      # Documentation for developers and contributors
│   └── dev/
│       ├── architecture.md    # This document
│       ├── DEVELOPMENT.md     # Development environment setup guide
│       └── heuristics.md      # Parser heuristics and coding standards
├── .devcontainer/             # VS Code devcontainer configuration and Dockerfiles
├── cli/                     
│   └── parser.py              # Standalone parser tool for testing and debugging
├── custom_components/      
│   └── watchman/           
│       ├── config_flow.py     # UI configuration flow
│       ├── coordinator.py     # DataUpdateCoordinator for state tracking and reporting
│       ├── hub.py             # Watchman database and scan engine orchestrator
│       ├── entity.py          # Base entity classes for Watchman entities
│       ├── sensor.py          # Sensor platform (missing entities/actions count)
│       ├── button.py          # Button entities (trigger manual report/scan)
│       ├── text.py            # Text entities (e.g. `watchman.ignored_labels`)
│       ├── services.py        # Service handlers (watchman.report)
│       ├── utils/             # Internal utility modules
│       │   ├── logger.py      # Structured logging with visual indentation
│       │   ├── parser_core.py # Core regex-based scanning logic
│       │   ├── report.py      # Report generation and formatting (table/text)
│       │   ├── yaml_loader.py # Optimized YAML loading for parser
│       │   └── utils.py       # General helper functions
└── tests/                     # Pytest-based regression suite
    ├── data/                  # Test fixtures (YAML, JSON configurations)
    └── tests/                 # Comprehensive unit and integration tests
```

## 6. Development Tips
* **Testing Regex**: When modifying the regex patterns in const.py, always test against edge cases like templating ({{ states('sensor.xyz') }}) and inline comments.
* **Performance**: Avoid blocking the event loop. File I/O operations should be run in an executor or strictly optimized.
