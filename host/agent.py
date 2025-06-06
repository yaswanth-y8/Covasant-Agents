from .host_agent import HostAgent
import httpx
import asyncio
http_client = httpx.AsyncClient()
host_agent = HostAgent(['http://localhost:8001','http://localhost:8002','http://localhost:8003'], http_client)
root_agent = host_agent.create_agent()