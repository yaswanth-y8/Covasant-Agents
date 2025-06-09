"""
A2A Server for the Reconciliation Specialist Agent.
"""
import os
import sys
import uvicorn

# Corrected import order for A2A components
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

current_script_dir = os.path.dirname(os.path.abspath(__file__))
agents_dir = os.path.abspath(os.path.join(current_script_dir, '..'))

if agents_dir not in sys.path:
    sys.path.insert(0, agents_dir)


from agent_executer import CustomStreamingAgentExecutor
from agent import ReconciliationAgent

RECONCILIATION_SKILL_DESCRIPTION = (
    'Compares pre-extracted data from an invoice and a purchase order '
    '(provided as JSON strings) to identify discrepancies, determine a match status, '
    'and provide a recommendation.'
)
RECONCILIATION_SKILL_EXAMPLES = [
    "Reconcile this invoice data with this PO data: [invoice_json_string] and "
    "[po_json_string].",
    "Compare the following invoice JSON against the PO JSON to find differences: "
    "invoice_details_json versus po_details_json.",
    "Perform reconciliation for invoice data: '...' and purchase order data: '...'",
    "I have the JSON output for an invoice and a PO. Can you reconcile them for me?"
]
RECONCILIATION_SKILL_TAGS = [
    'reconciliation', 'invoice', 'purchase order', 'comparison',
    'discrepancy', 'matching', 'finance', 'accounting'
]

# Agent Card Definition
RECONCILIATION_AGENT_CARD_DESCRIPTION = (
    'An A2A-wrapped agent that performs detailed comparison between pre-extracted '
    'invoice and purchase order JSON data using an underlying ADK agent to determine '
    'reconciliation status.'
)

if __name__ == '__main__':
    reconciliation_skill = AgentSkill(
        id='document_reconciliation',
        name='Reconcile Invoice and Purchase Order',
        description=RECONCILIATION_SKILL_DESCRIPTION,
        tags=RECONCILIATION_SKILL_TAGS,
        examples=RECONCILIATION_SKILL_EXAMPLES,
    )

    reconciliation_agent_card = AgentCard(
        name='Reconciliation Specialist Agent (A2A)',
        description=RECONCILIATION_AGENT_CARD_DESCRIPTION,
        url='http://localhost:8001/',
        version='1.0.0',
        defaultInputModes=['text'],
        defaultOutputModes=['text'],
        capabilities=AgentCapabilities(
            streaming=True
        ),
        skills=[reconciliation_skill],
    )
    request_handler = DefaultRequestHandler(
        agent_executor=CustomStreamingAgentExecutor(ReconciliationAgent),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=reconciliation_agent_card,
        http_handler=request_handler,
    )

    uvicorn.run(server.build(), host='0.0.0.0', port=8001)
