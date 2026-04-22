from __future__ import annotations

import os
import re
from typing import Any, Literal

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

NOTION_BASE_URL = "https://api.notion.com"
NOTION_VERSION = os.getenv("NOTION_VERSION", "2026-03-11")
NOTION_ACCESS_TOKEN = os.getenv("NOTION_ACCESS_TOKEN")

UUID_36_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
UUID_32_RE = re.compile(r"[0-9a-fA-F]{32}")

# Keep "database" as a legacy alias so older planners do not fail validation.
SearchObjectType = Literal["page", "data_source", "database"]

mcp = FastMCP(name="Notion")


def _join_plain_text(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    parts: list[str] = []
    for item in items:
        text = item.get("plain_text")
        if text:
            parts.append(text)
    return "".join(parts)


def _simplify_formula_value(formula: dict[str, Any] | None) -> Any:
    if not formula:
        return None

    formula_type = formula.get("type")
    if formula_type == "string":
        return formula.get("string")
    if formula_type == "number":
        return formula.get("number")
    if formula_type == "boolean":
        return formula.get("boolean")
    if formula_type == "date":
        return formula.get("date")
    return formula


def _simplify_rollup_value(rollup: dict[str, Any] | None) -> Any:
    if not rollup:
        return None

    rollup_type = rollup.get("type")
    if rollup_type == "number":
        return rollup.get("number")
    if rollup_type == "date":
        return rollup.get("date")
    if rollup_type == "array":
        values = []
        for item in rollup.get("array", []):
            values.append(_simplify_property_value(item))
        return values
    return rollup


def _simplify_people(people: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not people:
        return []
    simplified: list[dict[str, Any]] = []
    for person in people:
        simplified.append(
            {
                "id": person.get("id"),
                "name": person.get("name"),
                "type": person.get("type"),
            }
        )
    return simplified


def _simplify_files(files: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not files:
        return []
    simplified: list[dict[str, Any]] = []
    for f in files:
        entry = {
            "name": f.get("name"),
            "type": f.get("type"),
        }
        if f.get("type") == "file":
            entry["url"] = (f.get("file") or {}).get("url")
        elif f.get("type") == "external":
            entry["url"] = (f.get("external") or {}).get("url")
        simplified.append(entry)
    return simplified


def _simplify_property_value(prop: dict[str, Any]) -> Any:
    """
    Convert a raw Notion page property object into a plain JSON-friendly value.
    """
    prop_type = prop.get("type")

    if prop_type == "title":
        return _join_plain_text(prop.get("title"))

    if prop_type == "rich_text":
        return _join_plain_text(prop.get("rich_text"))

    if prop_type == "number":
        return prop.get("number")

    if prop_type == "select":
        select_value = prop.get("select")
        return None if select_value is None else select_value.get("name")

    if prop_type == "status":
        status_value = prop.get("status")
        return None if status_value is None else status_value.get("name")

    if prop_type == "multi_select":
        return [item.get("name") for item in prop.get("multi_select", [])]

    if prop_type == "date":
        return prop.get("date")

    if prop_type == "checkbox":
        return prop.get("checkbox")

    if prop_type == "url":
        return prop.get("url")

    if prop_type == "email":
        return prop.get("email")

    if prop_type == "phone_number":
        return prop.get("phone_number")

    if prop_type == "people":
        return _simplify_people(prop.get("people"))

    if prop_type == "files":
        return _simplify_files(prop.get("files"))

    if prop_type == "relation":
        return [item.get("id") for item in prop.get("relation", [])]

    if prop_type == "formula":
        return _simplify_formula_value(prop.get("formula"))

    if prop_type == "rollup":
        return _simplify_rollup_value(prop.get("rollup"))

    if prop_type == "created_time":
        return prop.get("created_time")

    if prop_type == "last_edited_time":
        return prop.get("last_edited_time")

    if prop_type == "created_by":
        user = prop.get("created_by") or {}
        return {"id": user.get("id"), "name": user.get("name")}

    if prop_type == "last_edited_by":
        user = prop.get("last_edited_by") or {}
        return {"id": user.get("id"), "name": user.get("name")}

    if prop_type == "unique_id":
        unique_id = prop.get("unique_id")
        if not unique_id:
            return None
        prefix = unique_id.get("prefix") or ""
        number = unique_id.get("number")
        return f"{prefix}{number}" if prefix else number

    if prop_type == "button":
        return None

    # Fallback: return the raw typed value if the type is unknown.
    return prop.get(prop_type)


def _simplify_notion_page(page: dict[str, Any]) -> dict[str, Any]:
    raw_properties = page.get("properties", {})
    simplified_properties: dict[str, Any] = {}

    for property_name, property_value in raw_properties.items():
        simplified_properties[property_name] = _simplify_property_value(property_value)

    return {
        "id": page.get("id"),
        "properties": simplified_properties,
    }

def _hyphenate_uuid(raw: str) -> str:
    raw = raw.replace("-", "").lower()
    if len(raw) != 32:
        raise ValueError(f"Expected 32 hex chars, got: {raw}")
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def normalize_notion_id(value: str) -> str:
    """
    Accepts:
    - raw UUID
    - 32-char Notion ID
    - Notion page/database/data-source URL
    - collection://<uuid>
    - {{collection://<uuid>}}
    """
    if not value or not value.strip():
        raise ValueError("A Notion ID or URL is required.")

    s = value.strip()
    s = s.replace("{{", "").replace("}}", "")

    if s.startswith("collection://"):
        s = s[len("collection://"):]

    match_36 = UUID_36_RE.search(s)
    if match_36:
        return match_36.group(0).lower()

    match_32 = UUID_32_RE.search(s)
    if match_32:
        return _hyphenate_uuid(match_32.group(0))

    raise ValueError(f"Could not extract a Notion UUID from: {value}")


def _normalize_search_object_type(
    object_type: SearchObjectType | None,
) -> Literal["page", "data_source"] | None:
    """
    Notion Search now accepts only 'page' or 'data_source'.
    Keep 'database' as a legacy alias and map it to 'data_source'.
    """
    if object_type is None:
        return None
    if object_type == "database":
        return "data_source"
    return object_type


def _plain_text_from_rich_text(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    parts: list[str] = []
    for item in items:
        text = item.get("plain_text")
        if text:
            parts.append(text)
    return "".join(parts).strip()


def _title_from_search_result(result: dict[str, Any]) -> str:
    """
    Search results return title-ish fields differently for pages vs data sources.
    """
    if result.get("object") == "data_source":
        return _plain_text_from_rich_text(result.get("title"))
    if result.get("object") == "page":
        props = result.get("properties", {})
        title_prop = props.get("title") or props.get("Name")
        if isinstance(title_prop, dict):
            if title_prop.get("type") == "title":
                return _plain_text_from_rich_text(title_prop.get("title"))
    return ""


def _normalize_title(title: str) -> str:
    return " ".join(title.strip().casefold().split())


class NotionClient:
    def __init__(
        self,
        access_token: str | None = None,
        notion_version: str = NOTION_VERSION,
    ):
        self.access_token = access_token or NOTION_ACCESS_TOKEN
        self.notion_version = notion_version
        self.session = requests.Session()

    @property
    def headers(self) -> dict[str, str]:
        if not self.access_token:
            raise RuntimeError("NOTION_ACCESS_TOKEN is missing.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Notion-Version": self.notion_version,
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: list[tuple[str, str]] | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{NOTION_BASE_URL}{path}"
        response = self.session.request(
            method=method,
            url=url,
            headers=self.headers,
            json=json_body,
            params=params,
            timeout=60,
        )

        if response.ok:
            if response.text:
                return response.json()
            return {}

        try:
            detail = response.json()
        except Exception:
            detail = response.text

        if response.status_code == 404:
            raise RuntimeError(
                f"Notion API 404 for {path}. "
                "This usually means the object does not exist or the parent database/page "
                "has not been shared with the integration. "
                f"Detail: {detail}"
            )

        raise RuntimeError(f"Notion API error {response.status_code}: {detail}")

    def search(
        self,
        query: str = "",
        object_type: SearchObjectType | None = None,
        page_size: int = 10,
        start_cursor: str | None = None,
    ) -> dict[str, Any]:
        page_size = max(1, min(page_size, 100))
        notion_object_type = _normalize_search_object_type(object_type)

        body: dict[str, Any] = {"page_size": page_size}
        if query:
            body["query"] = query
        if notion_object_type:
            body["filter"] = {"property": "object", "value": notion_object_type}
        if start_cursor:
            body["start_cursor"] = start_cursor

        return self._request("POST", "/v1/search", json_body=body)

    def retrieve_database(self, database_id_or_url: str) -> dict[str, Any]:
        database_id = normalize_notion_id(database_id_or_url)
        return self._request("GET", f"/v1/databases/{database_id}")

    def retrieve_data_source(self, data_source_id_or_url: str) -> dict[str, Any]:
        data_source_id = normalize_notion_id(data_source_id_or_url)
        return self._request("GET", f"/v1/data_sources/{data_source_id}")

    def retrieve_page(self, page_id_or_url: str) -> dict[str, Any]:
        page_id = normalize_notion_id(page_id_or_url)
        return self._request("GET", f"/v1/pages/{page_id}")

    def query_rows(
        self,
        data_source_id_or_url: str,
        filter: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 100,
        start_cursor: str | None = None,
        filter_properties: list[str] | None = None,
    ) -> dict[str, Any]:
        data_source_id = normalize_notion_id(data_source_id_or_url)
        page_size = max(1, min(page_size, 100))

        body: dict[str, Any] = {"page_size": page_size}
        if filter is not None:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        if start_cursor:
            body["start_cursor"] = start_cursor

        params: list[tuple[str, str]] | None = None
        if filter_properties:
            params = [("filter_properties[]", prop) for prop in filter_properties]

        return self._request(
            "POST",
            f"/v1/data_sources/{data_source_id}/query",
            json_body=body,
            params=params,
        )

    def create_page(
        self,
        data_source_id_or_url: str,
        properties: dict[str, Any],
        icon: dict[str, Any] | None = None,
        cover: dict[str, Any] | None = None,
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        data_source_id = normalize_notion_id(data_source_id_or_url)

        body: dict[str, Any] = {
            "parent": {
                "type": "data_source_id",
                "data_source_id": data_source_id,
            },
            "properties": properties,
        }
        if icon is not None:
            body["icon"] = icon
        if cover is not None:
            body["cover"] = cover
        if children is not None:
            body["children"] = children

        return self._request("POST", "/v1/pages", json_body=body)

    def update_page(
        self,
        page_id_or_url: str,
        properties: dict[str, Any] | None = None,
        icon: dict[str, Any] | None = None,
        cover: dict[str, Any] | None = None,
        archived: bool | None = None,
        in_trash: bool | None = None,
    ) -> dict[str, Any]:
        page_id = normalize_notion_id(page_id_or_url)

        body: dict[str, Any] = {}
        if properties is not None:
            body["properties"] = properties
        if icon is not None:
            body["icon"] = icon
        if cover is not None:
            body["cover"] = cover
        if archived is not None:
            body["archived"] = archived
        if in_trash is not None:
            body["in_trash"] = in_trash

        if not body:
            raise ValueError("Nothing to update.")

        return self._request("PATCH", f"/v1/pages/{page_id}", json_body=body)


client = NotionClient()

@mcp.tool()
def get_data_source_id_by_name(
    database_name: str,
    exact: bool = True,
    page_size: int = 20,
    max_pages: int = 5,
) -> dict[str, Any]:
    """
    Find a Notion data source by its visible database name and return the data source ID.

    What this tool does:
    - Searches Notion data sources using the provided name.
    - Compares titles in a case-insensitive and whitespace-normalized way.
    - Returns the matching `data_source_id`.
    - If multiple matches exist, returns candidate data sources instead of guessing.

    Parameters:
    - database_name:
        The visible name of the database/data source to search for.
        Example: "Products Raw Source DB"
    - exact:
        If True, only exact normalized title matches are accepted as valid matches.
        If False, the tool may return a single fuzzy candidate if only one exists.
    - page_size:
        Number of search results to fetch per request.
        Must be between 1 and 100.
    - max_pages:
        Maximum number of paginated search requests to make before stopping.

    How to use it:
    - Use this when you know the database name but not the data source ID.
    - If `found=True`, use `data_source_id` in `query_rows` or `upsert_data`.
    - If `found=False`, inspect `candidates` to see possible matches.

    Example:
    - get_data_source_id_by_name(
        database_name="Products Raw Source DB",
        exact=True,
        page_size=20,
        max_pages=3,
      )

    Returns:
    A dictionary containing:
    - found:
        True if exactly one usable data source match was found.
    - data_source_id:
        The resolved Notion data source ID when found=True.
    - title:
        The matched title when found=True.
    - url:
        The URL of the matched object when found=True.
    - match_type:
        One of:
        - "exact"
        - "single_candidate"
        - "ambiguous_exact"
        - "ambiguous_fuzzy"
        - "not_found"
    - candidates:
        A list of candidate matches, each including:
        - data_source_id
        - title
        - url
        - in_trash
    - message:
        Human-readable explanation when found=False.
    """
    wanted = _normalize_title(database_name)
    cursor: str | None = None
    pages_checked = 0

    exact_matches: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    while pages_checked < max_pages:
        resp = client.search(
            query=database_name,
            object_type="data_source",
            page_size=page_size,
            start_cursor=cursor,
        )
        pages_checked += 1

        for item in resp.get("results", []):
            if item.get("object") != "data_source":
                continue

            item_title = _title_from_search_result(item)

            record = {
                "data_source_id": item.get("id"),
                "title": item_title,
                "url": item.get("url"),
                "in_trash": item.get("in_trash", False),
            }
            candidates.append(record)

            if _normalize_title(item_title) == wanted:
                exact_matches.append(record)

        if exact and exact_matches:
            break

        if not resp.get("has_more") or not resp.get("next_cursor"):
            break

        cursor = resp["next_cursor"]

    if exact:
        unique_data_source_ids = {
            match["data_source_id"]: match
            for match in exact_matches
            if match.get("data_source_id")
        }

        if len(unique_data_source_ids) == 1:
            match = next(iter(unique_data_source_ids.values()))
            return {
                "found": True,
                "match_type": "exact",
                "data_source_id": match["data_source_id"],
                "title": match["title"],
                "url": match["url"],
                "candidates": candidates,
            }

        if len(unique_data_source_ids) > 1:
            return {
                "found": False,
                "match_type": "ambiguous_exact",
                "message": f"Multiple exact data source matches found for '{database_name}'.",
                "candidates": list(unique_data_source_ids.values()),
            }

    unique_candidate_data_source_ids = {
        candidate["data_source_id"]: candidate
        for candidate in candidates
        if candidate.get("data_source_id")
    }

    if len(unique_candidate_data_source_ids) == 1:
        match = next(iter(unique_candidate_data_source_ids.values()))
        return {
            "found": True,
            "match_type": "single_candidate",
            "data_source_id": match["data_source_id"],
            "title": match["title"],
            "url": match["url"],
            "candidates": candidates,
        }

    return {
        "found": False,
        "match_type": "not_found" if not candidates else "ambiguous_fuzzy",
        "message": (
            f"No exact data source titled '{database_name}' found."
            if not candidates
            else f"Found multiple candidate data sources for '{database_name}'."
        ),
        "candidates": candidates,
    }

@mcp.tool()
def get_page(page_id: str) -> dict[str, Any]:
    """Retrieve one Notion page by id or URL.

    What this tool does:
    - Normalizes the page reference.
    - Calls Notion page retrieval endpoint.
    - Returns the full page object (properties + metadata).

    Parameters:
    - page_id: Notion page reference in one of these forms:
        - Hyphenated UUID
        - 32-character UUID
        - Full Notion page URL

    Example:
    - get_page(page_id="https://www.notion.so/My-Page-0123456789abcdef0123456789abcdef")

    Returns:
    - Raw Notion page dictionary, commonly including:
        - id, object, created_time, last_edited_time
        - parent, in_trash, archived flags
        - properties map
    """
    return client.retrieve_page(page_id)


@mcp.tool()
def query_rows(
    data_source_id: str,
) -> dict[str, Any]:
    """
    Query rows from a Notion data source and return a simplified result shape.

    What this tool does:
    - Queries a Notion data source using default query behavior.
    - Removes most Notion page wrapper noise.
    - Returns only:
        - row id
        - property names
        - simplified property values

    Parameters:
    - data_source_id: Data source reference (UUID, URL, or collection://...).

    Example:
    - query_rows(
            data_source_id="collection://01234567-89ab-cdef-0123-456789abcdef",
        )

    Returns:
    - A simplified dictionary with:
        - results: list of rows
            each row has:
                - id
                - properties
        - has_more: bool
        - next_cursor: string or null

    Example returned row:
    {
        "id": "34ae7a94-867b-8105-b14e-f1ea64a9c128",
        "properties": {
            "Name": "Atlas Wireless Mouse",
            "Price": 100,
            "Description": "Ergonomic wireless mouse with silent-click buttons and USB receiver.",
            "Availability": "In stock",
            "SKU": "MOU-ATL-001"
        }
    }
    """

    raw_response = client.query_rows(
        data_source_id_or_url=data_source_id,
        filter=None,
        sorts=None,
        page_size=100,
        start_cursor=None,
        filter_properties=None,
    )

    simplified_results = [
        _simplify_notion_page(page)
        for page in raw_response.get("results", [])
        if page.get("object") == "page"
    ]

    return {
        "results": simplified_results,
        "has_more": raw_response.get("has_more", False),
        "next_cursor": raw_response.get("next_cursor"),
    }


@mcp.tool()
def upsert_data(
    data_source_id: str,
    properties: dict[str, Any],
    match_filter: dict[str, Any] | None = None,
    icon: dict[str, Any] | None = None,
    cover: dict[str, Any] | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create or update one row in a Notion data source.

    What this tool does:
    - If match_filter is provided, queries for an existing row.
    - If a row is found, updates the first match.
    - If no match is found (or no match_filter is given), creates a new row.

    Parameters:
    - data_source_id: Target data source reference (UUID, URL, or collection://...).
    - properties: Notion page-property payload in official Notion format.
    - match_filter: Optional Notion filter object used to find existing rows.
        Only the first matching row is updated.
    - icon: Optional icon payload for create/update operations.
    - cover: Optional cover payload for create/update operations.
    - children: Optional child blocks for creation. Ignored on update path.

    Example:
    - upsert_data(
            data_source_id="collection://01234567-89ab-cdef-0123-456789abcdef",
            properties={
                "Name": {"title": [{"text": {"content": "Task A"}}]},
                "Status": {"select": {"name": "Open"}},
            },
            match_filter={"property": "Name", "title": {"equals": "Task A"}},
        )

    Returns:
    - A dictionary with:
        - action: "updated" or "created"
        - page_id: id of the affected row
        - page: raw Notion page object from the write response
    """
    if match_filter is not None:
        existing = client.query_rows(
            data_source_id_or_url=data_source_id,
            filter=match_filter,
            page_size=1,
        )
        results = existing.get("results", [])
        if results:
            page_id = results[0]["id"]
            updated = client.update_page(
                page_id_or_url=page_id,
                properties=properties,
                icon=icon,
                cover=cover,
            )
            return {
                "action": "updated",
                "page_id": page_id,
                "page": updated,
            }

    created = client.create_page(
        data_source_id_or_url=data_source_id,
        properties=properties,
        icon=icon,
        cover=cover,
        children=children,
    )
    return {
        "action": "created",
        "page_id": created.get("id"),
        "page": created,
    }


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8020)