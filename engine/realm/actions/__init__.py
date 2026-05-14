"""Player-facing action handlers — thin validation + dispatch.

Every action returns ``ActionResult`` (``ActionOk`` on success,
``ActionErr(reason="...")`` on expected failure). Routes in
``realm.api.*`` should NOT contain game logic; they call into this
package.

Submodules:
  * ``realm.actions._shared``               — ActionOk / ActionErr / ActionResult types
  * ``realm.actions.plot_actions``          — claim_plot, survey_plot, survey-report market
  * ``realm.actions.business_actions``      — register_business
  * ``realm.actions.employment_actions``    — hire_*, tick_stub_employment, poach_worker
  * ``realm.actions.production_actions``    — start_production_on_plot, harvest helpers
  * ``realm.actions.shipping_actions``      — register_route, revise_route_fee
  * ``realm.actions.assay_actions``         — Tier-2 mineral assay (formerly ``realm.assay``)
  * ``realm.actions.deep_survey_actions``   — Deep survey (formerly ``realm.deep_survey``)

Anything previously imported from the flat ``realm.actions`` module is
re-exported here so ``from realm.actions import claim_plot`` etc. keep
working.
"""

from realm.actions._shared import ActionErr, ActionOk, ActionResult  # noqa: F401
from realm.actions.business_actions import (  # noqa: F401
    BUSINESS_NAME_MAX_LEN,
    BUSINESS_NAME_MIN_LEN,
    BUSINESS_REGISTRATION_FEE_CENTS,
    register_business,
)
from realm.actions.employment_actions import (  # noqa: F401
    HIRABLE_NPCS,
    hire_catalog_public,
    hire_worker_stub,
    poach_worker,
    request_labor_transport_action,
    tick_stub_employment,
)
from realm.actions.plot_actions import (  # noqa: F401
    SURVEY_COST_CENTS,
    buy_survey_report,
    cancel_survey_report_listing,
    claim_plot,
    create_survey_report,
    list_survey_report,
    plot_by_id,
    survey_plot,
    transfer_survey_report,
)
from realm.actions.production_actions import (  # noqa: F401
    harvest_plot_output_stock,
    start_production_on_plot,
)
from realm.actions.shipping_actions import (  # noqa: F401
    register_route,
    revise_route_fee,
)
