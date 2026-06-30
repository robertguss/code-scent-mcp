from fastmcp import FastMCP

from codescent.mcp.answer_pack_tools import register_answer_pack_tools
from codescent.mcp.architecture_tools import register_architecture_tools
from codescent.mcp.context_tools import register_context_tools
from codescent.mcp.finding_tools import register_finding_tools
from codescent.mcp.guide_tools import register_guide_tools
from codescent.mcp.planning_tools import register_planning_tools
from codescent.mcp.prompts import register_prompts
from codescent.mcp.repo_tools import register_repo_tools
from codescent.mcp.result_tools import register_result_tools
from codescent.mcp.risk_tools import register_risk_tools
from codescent.mcp.search_tools import register_search_tools
from codescent.mcp.session_stats_tools import register_session_stats_tools
from codescent.mcp.subjective_tools import register_subjective_tools

mcp = FastMCP(name="CodeScent")
register_repo_tools(mcp)
register_search_tools(mcp)
register_context_tools(mcp)
register_answer_pack_tools(mcp)
register_architecture_tools(mcp)
register_result_tools(mcp)
register_finding_tools(mcp)
register_planning_tools(mcp)
register_risk_tools(mcp)
register_session_stats_tools(mcp)
register_guide_tools(mcp)
register_subjective_tools(mcp)
register_prompts(mcp)


def mcp_available() -> bool:
    return hasattr(mcp, "run")


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
