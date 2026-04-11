# tools 
fastmcp run tools/websearch.py --transport streamable-http --host 0.0.0.0 --port 8003 &


# agent
uvicorn agent.main:app --host 0.0.0.0 --port 8090 --reload

wait
