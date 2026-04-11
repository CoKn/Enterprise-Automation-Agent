from fastmcp import FastMCP
from typing import List
from bs4.element import AttributeValueList
import requests
from ddgs import DDGS
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# MCP server
mcp = FastMCP(
    name="Websearch and scraping"
)

# MCP Tools
def duckduckgo_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """
    Search DuckDuckGo and return structured results.

    Args:
        query: The search term.
        max_results: Maximum number of results to return.

    Returns:
        A list of result objects with keys: title, href, body.
        This is a real JSON array (not a string), suitable for schema validation.
    """
    results: list[dict[str, str]] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            results.append({
                "title": item.get("title", ""),
                "href": item.get("href", ""),
                "body": item.get("body", ""),
            })
    return results

def get_website_urls(url: str) -> List[str | AttributeValueList | None]:
    """Extracts all hyperlinks from a webpage.

        This function fetches a webpage from the provided URL, parses the HTML content,
        and extracts all hyperlinks (anchor tags) found on the page. It processes relative
        URLs to convert them to absolute URLs by prepending the base URL.

        Args:
            url: The complete URL of the webpage to fetch (e.g., 'https://example.com')

        Returns:
            A list of URLs extracted from the webpage. Each element can be a string URL,
            a BeautifulSoup AttributeValueList, or None if the href attribute is missing.

        Raises:
            requests.RequestException: If the HTTP request fails
    """
    r = requests.get(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    all_anchors = soup.find_all("a")
    urls = []
    for anchor in all_anchors:
        if anchor.get("href", "") == "#":
            continue

        elif anchor.get("href", "").startswith('/'):
            if url.endswith('/'):
                urls.append(url[:-1] + anchor.get("href"))
            else:
                urls.append(url + anchor.get("href"))
        else:
            urls.append(anchor.get("href"))
    return urls[:5]


def get_website_content(url: str) -> str:
    """Fetches a webpage and converts it to clean markdown text.

    This function retrieves HTML content from the specified URL, removes images
    and SVG elements, then converts the cleaned HTML to markdown format.

    Args:
        url: The complete URL of the webpage to fetch

    Returns:
        A string containing the markdown representation of the webpage with
        images and SVG elements removed.

    Raises:
        requests.RequestException: If the HTTP request fails
    """
    r = requests.get(url)
    soup = BeautifulSoup(r.text, 'html.parser')

    # Remove every <img> tag entirely
    for img_tag in soup.find_all('img'):
        img_tag.decompose()

    # Remove every <svg> tag entirely
    for svg_tag in soup.find_all('svg'):
        svg_tag.decompose()

    # Remove any <a> that wraps only an <img> or <svg> (so no “image links” remain)
    for a_tag in soup.find_all('a'):
        if a_tag.find('img') or a_tag.find('svg'):
            a_tag.decompose()

    extracted: list[str] = []

    # Include high-signal tags for navigation + content extraction in DOM order.
    target_tags = [
        'title', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'li', 'a',
        'nav', 'main', 'section', 'article', 'aside',
        'button', 'form', 'label', 'input', 'textarea', 'select', 'option',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
    ]

    for tag in soup.find_all(target_tags):
        name = tag.name
        text = tag.get_text(' ', strip=True)

        if name == 'a':
            href = tag.get('href')
            if href and text:
                extracted.append(f"LINK: {text} -> {urljoin(url, href)}")
            elif href:
                extracted.append(f"LINK: {urljoin(url, href)}")
            continue

        if name == 'button':
            if text:
                extracted.append(f"BUTTON: {text}")
            continue

        if name == 'form':
            action = urljoin(url, tag.get('action') or url)
            method = (tag.get('method') or 'get').upper()
            extracted.append(f"FORM: method={method} action={action}")
            continue

        if name in {'input', 'textarea', 'select'}:
            field_name = tag.get('name') or ''
            field_type = tag.get('type') or name
            placeholder = tag.get('placeholder') or ''
            value = tag.get('value') or ''
            extracted.append(
                f"FIELD: name={field_name} type={field_type} placeholder={placeholder} value={value}".strip()
            )
            continue

        if name == 'option':
            value = tag.get('value') or ''
            if text or value:
                extracted.append(f"OPTION: text={text} value={value}".strip())
            continue

        if name in {'th', 'td'}:
            if text:
                extracted.append(f"{name.upper()}: {text}")
            continue

        if text:
            extracted.append(f"{name.upper()}: {text}")

    # Keep insertion order while dropping duplicates to reduce repetition.
    unique_extracted = list(dict.fromkeys(extracted))
    return '\n'.join(unique_extracted)[:6000]


def get_page_title(url: str) -> str:
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.find("title")
    return title_tag.get_text(strip=True) if title_tag else ""


def find_click_target(soup: BeautifulSoup, target: str, click_type: str):
    target_lower = target.strip().lower()

    if click_type == "link":
        for anchor in soup.find_all("a"):
            text = anchor.get_text(" ", strip=True).lower()
            href = (anchor.get("href") or "").lower()
            if target_lower == text or target_lower == href or target_lower in text:
                return {"kind": "link", "element": anchor}

    if click_type == "button":
        for button in soup.find_all("button"):
            text = button.get_text(" ", strip=True).lower()
            value = (button.get("value") or "").lower()
            if target_lower == text or target_lower == value or target_lower in text:
                return {"kind": "button", "element": button}

    return None


@mcp.tool()
def search_web(query: str, max_results: int = 2) -> list[dict[str , str]]:
    """Search the web using DuckDuckGo and return each result with scraped markdown content.

    Args:
        query: Search phrase to send to DuckDuckGo.
        max_results: Maximum number of SERP entries to enrich (defaults to 2).

    Returns:
        A list where each item includes the DuckDuckGo fields (title, href, body)
        plus a ``content`` key containing the cleaned markdown from the result URL.
    """
    results: list[dict[str, str]] = duckduckgo_search(query=query, max_results=max_results)
    web_content: list[dict[str , str]] = []
    for website in results:
        url = website.get("href", None)
        if not url:
            continue
        content: str = get_website_content(url=url)
        data = website | {"content": content}
        web_content.append(data)

    return web_content


@mcp.tool()
def open_website(url: str) -> dict[str, str]:
    """Open a specific website by URL and return cleaned page content.

    Args:
        url: The webpage URL to fetch and read.

    Returns:
        A dictionary containing the source URL and a cleaned text snapshot of the page.
    """
    content: str = get_website_content(url=url)
    return {"url": url, "content": content}


@mcp.tool()
def navigate_website(url: str, target: str, click_type: str = "link") -> dict[str, str]:
    """Navigate to a new page by clicking a link or button on a webpage.

    Args:
        url: The current page URL to inspect.
        target: Visible link text, button text, or href/value to match.
        click_type: Use "link" to follow anchors or "button" to submit a simple form button.

    Returns:
        A dictionary with the navigation result, including the destination URL and cleaned content.

    Notes:
        This handles standard links and basic HTML forms. It does not execute JavaScript-driven UI.
    """
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    click = find_click_target(soup, target=target, click_type=click_type)

    if not click:
        return {
            "url": url,
            "target": target,
            "click_type": click_type,
            "error": "No matching link or button was found on the page.",
            "content": get_website_content(url=url),
        }

    element = click["element"]

    if click["kind"] == "link":
        href = element.get("href")
        if not href:
            return {
                "url": url,
                "target": target,
                "click_type": click_type,
                "error": "Matched link did not contain a usable href.",
                "content": get_website_content(url=url),
            }

        next_url = urljoin(url, href)
        return {
            "url": next_url,
            "target": target,
            "click_type": click_type,
            "title": get_page_title(next_url),
            "content": get_website_content(next_url),
        }

    form = element.find_parent("form")
    if form is None:
        return {
            "url": url,
            "target": target,
            "click_type": click_type,
            "error": "Matched button is not inside a form, so there is nothing to submit.",
            "content": get_website_content(url=url),
        }

    form_action = urljoin(url, form.get("action") or url)
    form_method = (form.get("method") or "get").lower()
    payload: dict[str, str] = {}

    for input_tag in form.find_all(["input", "textarea", "select"]):
        name = input_tag.get("name")
        if not name:
            continue

        if input_tag.name == "input":
            input_type = (input_tag.get("type") or "text").lower()
            if input_type in {"submit", "button", "reset", "file"}:
                continue
            payload[name] = input_tag.get("value", "")
        elif input_tag.name == "textarea":
            payload[name] = input_tag.text or ""
        else:
            option = input_tag.find("option", selected=True) or input_tag.find("option")
            payload[name] = option.get("value", option.get_text(strip=True)) if option else ""

    button_name = element.get("name")
    button_value = element.get("value") or element.get_text(" ", strip=True)
    if button_name:
        payload[button_name] = button_value

    if form_method == "post":
        next_response = requests.post(form_action, data=payload)
    else:
        next_response = requests.get(form_action, params=payload)

    next_url = next_response.url
    return {
        "url": next_url,
        "target": target,
        "click_type": click_type,
        "title": get_page_title(next_url),
        "content": get_website_content(next_url),
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8003)
