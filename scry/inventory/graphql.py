"""Extractor for GraphQL operations from source files."""

from __future__ import annotations

import re

from scry.inventory._utils import glob_source_files
from scry.models.config import ProjectConfig
from scry.models.enums import OperationType
from scry.models.surface import AppSurface, GraphQLOperation


def _extract_raw_query(content: str, op_keyword_pos: int) -> str:
    """Extract the full GraphQL operation text using brace-matching.

    Starting from `op_keyword_pos` (position of the query/mutation keyword),
    tracks brace depth to capture the complete operation body.
    """
    # Find the first opening brace after the operation keyword
    brace_pos = content.find("{", op_keyword_pos)
    if brace_pos == -1:
        return ""

    # Track brace depth to find matching close
    depth = 0
    for i in range(brace_pos, len(content)):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                return content[op_keyword_pos : i + 1]

    return content[op_keyword_pos:]


def _extract_top_level_fields(raw_query: str) -> list[str]:
    """Extract top-level field names from a GraphQL operation body.

    Parses the first level of nesting inside the operation's outer braces.
    Uses a pre-update depth check: only lines at depth 0 (before processing
    the current line's braces) are considered top-level fields.
    """
    # Find the operation body (content between first { and its matching })
    first_brace = raw_query.find("{")
    if first_brace == -1:
        return []

    # Find matching close brace
    depth = 0
    body_end = len(raw_query)
    for i in range(first_brace, len(raw_query)):
        if raw_query[i] == "{":
            depth += 1
        elif raw_query[i] == "}":
            depth -= 1
            if depth == 0:
                body_end = i
                break

    body = raw_query[first_brace + 1 : body_end]

    # Extract field names at depth 0 within the body
    fields: list[str] = []
    pre_depth = 0
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Only extract fields when we're at the top level (depth 0)
        if pre_depth == 0:
            field_match = re.match(r"(\w+)", stripped)
            if field_match:
                field_name = field_match.group(1)
                # Skip GraphQL keywords
                if field_name not in ("query", "mutation", "fragment", "subscription"):
                    fields.append(field_name)

        # Update depth AFTER the extraction check
        pre_depth += stripped.count("{") - stripped.count("}")

    return fields


class GraphQLExtractor:
    """Extracts GraphQL operations from tagged template literals in source files."""

    def extract(self, config: ProjectConfig, surface: AppSurface) -> AppSurface:
        """Scan source files for GraphQL operations and populate the surface."""
        tag = re.escape(config.graphql_tag)
        pattern = re.compile(
            tag + r"[\s\S]*?(query|mutation)\s+(\w+)",
            re.DOTALL,
        )

        operations: list[GraphQLOperation] = []

        for file_path in glob_source_files(config):
            content = file_path.read_text(encoding="utf-8")
            for match in pattern.finditer(content):
                op_type_str = match.group(1)
                op_name = match.group(2)

                op_type = OperationType.QUERY if op_type_str == "query" else OperationType.MUTATION

                # Use the position of the operation keyword directly,
                # not the tag position — avoids matching wrong keywords
                # if comments mention other operations between tag and keyword.
                op_keyword_pos = match.start(1)
                raw_query = _extract_raw_query(content, op_keyword_pos)
                fields = _extract_top_level_fields(raw_query)

                operations.append(
                    GraphQLOperation(
                        name=op_name,
                        operation_type=op_type,
                        file=file_path,
                        fields=fields,
                        raw_query=raw_query,
                    )
                )

        surface.graphql_operations = operations
        return surface
