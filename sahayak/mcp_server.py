"""MCP server exposing Sahayak's tools to any MCP client (Claude desktop, Cursor, etc.).

Run:   python -m sahayak.mcp_server          (stdio transport)

Claude desktop config (claude_desktop_config.json):
{
  "mcpServers": {
    "sahayak": {
      "command": "C:\\\\Users\\\\<you>\\\\Documents\\\\scheme-sahayak\\\\.venv\\\\Scripts\\\\python.exe",
      "args": ["-m", "sahayak.mcp_server"],
      "cwd": "C:\\\\Users\\\\<you>\\\\Documents\\\\scheme-sahayak"
    }
  }
}
"""
from __future__ import annotations

from typing import Optional

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from .tools import Toolbox

mcp = _Server("sahayak")
_tb = Toolbox()


@mcp.tool()
def search_schemes(query: str, top_k: int = 5) -> list[dict]:
    """Find Indian government schemes relevant to a need, e.g. 'widow pension' or 'girl child savings'."""
    return _tb.search_schemes(query, top_k)


@mcp.tool()
def get_scheme_details(scheme_id: str) -> dict:
    """Benefits, documents, how to apply and the official source for one scheme."""
    return _tb.get_scheme_details(scheme_id)


@mcp.tool()
def check_eligibility(profile: dict, scheme_ids: Optional[list[str]] = None) -> dict:
    """Decide eligibility with deterministic rules. The ONLY way to decide eligibility.

    profile keys (all optional; pass only facts the user stated): age, gender (male/female/other),
    state, marital_status (single/married/widowed/divorced/separated), bpl, annual_income (rupees per year),
    monthly_income (rupees per month; give whichever the user stated, rules convert), household_size,
    ever_income_tax_payer, income_tax_payer_last_year, is_current_income_tax_payer, has_bank_account,
    owns_cultivable_land, land_holding_hectares, is_govt_employee, monthly_pension, household_has_lpg,
    pregnant_or_lactating, in_regular_govt_employment, children (list of {age, gender}),
    occupation (street_vendor/artisan_craftsperson/fisherman/coir_worker/agricultural_labourer/farmer/
    construction_worker/domestic_worker/small_trader_shopkeeper/self_employed/salaried_private/govt_employee/
    student/unemployed/homemaker/retired/other), is_unorganised_worker, is_epfo_esic_nps_member,
    disability_percentage (0-100), social_category (general/obc/sc/st/ews), ration_card_type (aay/phh/apl/none),
    breadwinner_deceased, breadwinner_age_at_death, house_type (pucca/kutcha/none_homeless), has_pucca_house.
    Unknown keys and out-of-range values are rejected with an error.
    Returns schemes grouped into eligible / need_info (with missing fields) / not_eligible (with reasons and caveats;
    a caveat may say the person can still qualify another way).
    """
    return _tb.check_eligibility(profile, scheme_ids)


@mcp.resource("schemes://list")
def list_schemes() -> str:
    """All scheme ids and names."""
    return "\n".join(f"{s.id}: {s.name}" for s in _tb.schemes.values())


def main():
    mcp.run()


if __name__ == "__main__":
    main()
