"""Main entry point for the Data Ingestion Agent A2A server."""

import os
import sys

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

# Add parent directory to path if needed
current_script_dir = os.path.dirname(os.path.abspath(__file__))
agents_dir = os.path.abspath(os.path.join(current_script_dir, '..'))

if agents_dir not in sys.path:
    sys.path.insert(0, agents_dir)

from agent import DataIngestionAgent  
from agent_executer import CustomStreamingAgentExecutor


if __name__ == '__main__':
    data_ingestion_skill = AgentSkill(
        id='document_ingestion',
        name='Process and Store Document',
        description=(
            'Extracts data from a specified document file (e.g., invoice, '
            'purchase order), processes it, and stores it in the database.'
        ),
        tags=[
            'document', 'ingestion', 'data extraction', 'invoice', 'purchase order',
            'database', 'storage', 'parsing', 'ocr'
        ],
        examples=[
            "Process the invoice located at '/path/to/my_invoice.pdf'.",
            "Ingest the purchase order from 'data/po_123.docx' and store its details.",
            "I need to upload and process an invoice. The file is 'invoices/new_inv.pdf'"
            " and it's an 'invoice' type.",
            "Store this document: type is 'purchase_order', file path is 'C:\\docs\\po_final.png'."
        ],
    )

    data_ingestion_agent_card = AgentCard(
        name='Data Ingestion Specialist Agent (A2A)',
        description=(
            'An A2A-wrapped agent specialized in ingesting raw documents '
            '(like invoices and purchase orders), extracting their data via an '
            'underlying ADK agent, and storing them into a database.'
        ),
        url='http://localhost:8002/',
        version='1.0.0',
        defaultInputModes=['text'],
        defaultOutputModes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[data_ingestion_skill],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=CustomStreamingAgentExecutor(DataIngestionAgent),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=data_ingestion_agent_card,
        http_handler=request_handler,
    )

    uvicorn.run(server.build(), host='0.0.0.0', port=8002)
