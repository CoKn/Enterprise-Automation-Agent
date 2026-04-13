from urllib.parse import urljoin

from bs4 import BeautifulSoup
from ddgs import DDGS
from fastmcp import FastMCP
import markdownify

import requests


mcp = FastMCP(name="Web Navigator")


def search_web(query: str, max_results=2):
    results: list[dict[str, str]] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            results.append({
                "title": item.get("title", ""),
                "href": item.get("href", ""),
                "body": item.get("body", ""),
            })
    return results


@mcp.tool()
def open_page(url: str):
    response = requests.get(url=url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    all_anchors = soup.find_all("a")
    urls = []
    seen = set()
    for anchor in all_anchors:
        href = (anchor.get("href") or "").strip()
        if not href or href == "#":
            continue

        # gnore non-navigable pseudo links.
        if href.startswith(("javascript:", "mailto:", "tel:")):
            continue

        absolute_url = urljoin(url, href)
        if absolute_url in seen:
            continue

        seen.add(absolute_url)
        urls.append(absolute_url)

    # convert html to markdown
    h = markdownify.markdownify(soup, heading_style="ATX")

    navigation_section = "\n".join(urls)
    return (
        "navigation:\n"
        f"{navigation_section}\n\n"
        "page_content:\n"
        f"{h.strip()}"
    )

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8003)