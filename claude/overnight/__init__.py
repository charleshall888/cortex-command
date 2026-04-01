"""Overnight orchestration pipeline for multi-feature development sessions.

Manages long-running overnight sessions that execute multiple features in
rounds, with state tracking, pause/resume capability, and deferred question
handling.

Entry point: python3 -m claude.overnight (future)
"""

__version__ = "0.1.0"

from claude.overnight.backlog import (  # noqa: F401
    BacklogItem,
    Batch,
    SelectionResult,
    filter_ready,
    parse_backlog_dir,
    select_overnight_batch,
)
from claude.overnight.plan import (  # noqa: F401
    bootstrap_session,
    initialize_overnight_state,
    render_session_plan,
    validate_target_repos,
    write_session_plan,
)
from claude.overnight.deferral import (  # noqa: F401
    SEVERITIES,
    SEVERITY_BLOCKING,
    SEVERITY_INFORMATIONAL,
    SEVERITY_NON_BLOCKING,
    DeferralQuestion,
    read_deferrals,
    read_deferrals_for_feature,
    summarize_deferrals,
    write_deferral,
)
from claude.overnight.batch_plan import (  # noqa: F401
    generate_batch_plan,
    map_pipeline_results,
)
from claude.overnight.batch_runner import (  # noqa: F401
    BatchConfig,
    BatchResult,
    run_batch,
)
from claude.overnight.report import (  # noqa: F401
    ReportData,
    collect_report_data,
    generate_and_write_report,
    generate_report,
    write_report,
)
from claude.overnight.throttle import (  # noqa: F401
    ConcurrencyManager,
    ThrottleConfig,
    load_throttle_config,
    throttled_dispatch,
)
