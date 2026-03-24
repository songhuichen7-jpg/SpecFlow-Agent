"""Built-in MCP tool handlers."""

from specflow.mcp.tools.quality import check_types, run_build, run_lint, run_tests
from specflow.mcp.tools.scaffold import create_project_skeleton, init_git_repo
from specflow.mcp.tools.spec import export_spec_summary, read_spec, validate_spec_completeness
from specflow.mcp.tools.template import (
    get_template_content,
    list_available_templates,
    search_templates,
)
from specflow.mcp.tools.workspace import delete_file, list_directory, read_file, write_file

__all__ = [
    "check_types",
    "create_project_skeleton",
    "delete_file",
    "export_spec_summary",
    "get_template_content",
    "init_git_repo",
    "list_available_templates",
    "list_directory",
    "read_file",
    "read_spec",
    "run_build",
    "run_lint",
    "run_tests",
    "search_templates",
    "validate_spec_completeness",
    "write_file",
]
