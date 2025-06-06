import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore # Good for simplicity here
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
import sys
import os

current_script_dir = os.path.dirname(os.path.abspath(__file__))

agents_dir = os.path.abspath(os.path.join(current_script_dir, '..'))

if agents_dir not in sys.path:
    sys.path.insert(0, agents_dir)


from Agents.agent_executer import (
    AgentExecutor,
)
from agent import ReconciliationAgent


if __name__ == '__main__':
    reconciliation_skill = AgentSkill(
            id='document_reconciliation', # Unique ID for the skill
            name='Reconcile Invoice and Purchase Order',
            description='Compares pre-extracted data from an invoice and a purchase order (provided as JSON strings) to identify discrepancies, determine a match status, and provide a recommendation.',
            tags=['reconciliation', 'invoice', 'purchase order', 'comparison', 'discrepancy', 'matching', 'finance', 'accounting'],
            examples=[
                "Reconcile this invoice data with this PO data: [invoice_json_string] and [po_json_string].",
                "Compare the following invoice JSON against the PO JSON to find differences: invoice_details_json versus po_details_json.",
                "Perform reconciliation for invoice data: '...' and purchase order data: '...'",
                "I have the JSON output for an invoice and a PO. Can you reconcile them for me?"
            ],
        )

        # Define the AgentCard for this A2A agent
    reconciliation_agent_card = AgentCard(
            name='Reconciliation Specialist Agent (A2A)',
            description='An A2A-wrapped agent that performs detailed comparison between pre-extracted invoice and purchase order JSON data using an underlying ADK agent to determine reconciliation status.',
            url='http://localhost:8001/', # Assuming this agent runs on a different port or endpoint
            version='1.0.0',
            defaultInputModes=['text'], # Agent expects text input containing the two JSON strings
            defaultOutputModes=['text'], # Agent streams a JSON result as text
            capabilities=AgentCapabilities(
                streaming=True # ReconciliationAgentWrapper.reconcile_documents is an async iterable
            ),
            skills=[reconciliation_skill], # Reference the new skill defined above
            # supportsAuthenticatedExtendedCard=False, # Set to True if implemented
        )

    request_handler = DefaultRequestHandler(
    agent_executor=AgentExecutor(ReconciliationAgent),
    task_store=InMemoryTaskStore(),
)

    server = A2AStarletteApplication(
        agent_card=reconciliation_agent_card,
        http_handler=request_handler,
    )

    uvicorn.run(server.build(), host='0.0.0.0', port=8001)