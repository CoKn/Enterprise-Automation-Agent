from fastmcp import FastMCP


mcp = FastMCP(name="Notion")


mcp.tool()
def get_serch_workspace():
    ...

mcp.tool()
def query_database():
    ...

mcp.tool()
def get_page():
    ...

mcp.tool()
def clean_data():
    ...

mcp.tool()
def upsert_data():
    ...



if __name__ == '__main__':
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8020)