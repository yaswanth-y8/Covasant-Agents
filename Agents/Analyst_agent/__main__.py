"""Entry point for launching the Analyst Agent A2A server."""

import os
import sys

import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

current_script_dir = os.path.dirname(os.path.abspath(__file__))
agents_dir = os.path.abspath(os.path.join(current_script_dir, '..'))

if agents_dir not in sys.path:
    sys.path.insert(0, agents_dir)

from agent import AnalystAgent
from agent_executer import CustomStreamingAgentExecutor

if __name__ == '__main__':
    analyst_query_skill = AgentSkill(
        id='database_query',
        name='Query Document Database',
        description=(
            "Queries a database of invoices and purchase orders based on user criteria such as "
            "vendor name, date range, or document type and provide summaries or lists of documents."
        ),
        tags=[
            'database', 'query', 'analytics', 'reporting',
            'invoice', 'purchase order', 'vendor', 'date range', 'summary'
        ],
        examples=[
            "How many invoices do we have for 'ACME Corp'?",
            "What's the total amount for purchase orders/ invoices from 'Supplier X' between "
            "2023-01-01 and 2023-03-31?",
            "List the last 5 purchase orders we received in January.",
            "Show me invoices from 'Beta Inc' for last month.",
            "Get a count of all purchase orders created this year.",
            "Find purchase orders for 'Tech Solutions Ltd'."
        ],
    )

    analyst_agent_card = AgentCard(
        name='Database Analyst Agent (A2A)',
        description=(
            'An A2A-wrapped agent that allows users to query a database of invoices and '
            'purchase orders using natural language. '
            'It can provide counts, total amount, and lists of documents based on various criteria.'
        ),
        url='http://localhost:8003/',
        version='1.0.0',
        defaultInputModes=['text'],
        defaultOutputModes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[analyst_query_skill],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=CustomStreamingAgentExecutor(AnalystAgent),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=analyst_agent_card,
        http_handler=request_handler,
    )

    uvicorn.run(server.build(), host='0.0.0.0', port=8003)
