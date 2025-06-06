import base64
import json
import uuid

from typing import List, Dict # Added Dict for type hints

import httpx

from a2a.client import A2ACardResolver 
from a2a.types import (
    AgentCard,
    DataPart, # Make sure DataPart is correctly imported or defined
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    Task,
    TaskState,
    TextPart,
)
from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from google.genai import types 
from .remote_agent_connection import RemoteAgentConnections


class HostAgent:
    def __init__(
        self,
        remote_agent_addresses: list[str],
        http_client: httpx.AsyncClient,
    ):
        self.httpx_client = http_client
        self.remote_agent_addresses = remote_agent_addresses 
        self.remote_agent_connections: Dict[str, RemoteAgentConnections] = {}
        self.cards: Dict[str, AgentCard] = {}
        self.agents: str = "Remote agent list not yet initialized. Use 'list_remote_agents' tool to populate."
        self._initialized: bool = False

    async def _ensure_initialized(self):
        """Ensures that remote agent connections are initialized asynchronously."""
        if self._initialized:
            return

        # Temporary dicts to build before assigning to self to ensure atomicity of update
        cards_temp: Dict[str, AgentCard] = {}
        connections_temp: Dict[str, RemoteAgentConnections] = {}

        for address in self.remote_agent_addresses:
            card_resolver = A2ACardResolver(self.httpx_client, address)
            try:
                card = await card_resolver.get_agent_card()  # <-- Key fix: await the coroutine
                # print("this is card",card)
            except Exception as e:
                # It's good practice to log this error appropriately
                print(f"Warning: Failed to retrieve agent card from {address}. Error: {e}")
                continue  # Skip this agent and try the next one

            if not hasattr(card, 'name') or not card.name:
                print(f"Warning: Agent card from {address} is missing a name, skipping.")
                continue

            remote_connection = RemoteAgentConnections(self.httpx_client, card)
            connections_temp[card.name] = remote_connection
            # print("connections",connections_temp)
            cards_temp[card.name] = card
        
        self.cards = cards_temp
        self.remote_agent_connections = connections_temp

        agent_info_list = []
        for ra_card in self.cards.values():
            agent_info_list.append(json.dumps({'name': ra_card.name, 'description': ra_card.description}))
        
        if agent_info_list:
            # print("agent info list",agent_info_list)
            self.agents = '\n'.join(agent_info_list)
        else:
            self.agents = "No remote agents are currently available or could be initialized."
            
        self._initialized = True
        return self.cards

    async def register_agent_card(self, card: AgentCard):
        """Registers a new agent card dynamically. Ensures initialization first."""
        await self._ensure_initialized() # Ensure base initialization is done

        # Add or update the new card
        remote_connection = RemoteAgentConnections(self.httpx_client, card)
        self.remote_agent_connections[card.name] = remote_connection
        self.cards[card.name] = card
        
        agent_info_list = []
        for ra_card_loop in self.cards.values(): # Iterate over all current cards
            agent_info_list.append(json.dumps({'name': ra_card_loop.name, 'description': ra_card_loop.description}))
        
        if agent_info_list:
            print("agent info list",agent_info_list)
            self.agents = '\n'.join(agent_info_list)
        else:
            self.agents = "No remote agents are currently available." # Should be rare if adding a card

    def create_agent(self) -> Agent:
        return Agent(
            model='gemini-2.0-flash-001',
            name='host_agent',
            instruction=self.root_instruction, # Pass the method to be called for instruction
            description=(
                'This agent orchestrates the decomposition of the user request into'
                ' tasks that can be performed by the child agents.'
            ),
            tools=[
                self.list_remote_agents, # This method is now async
                self.send_message,       # This method was already async
            ],
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        current_agent_state = self.check_state(context)
        return f"""You are an expert orchestrator for document processing and analysis workflows.
                    **Startup & Greeting:**
                    - When the user first interacts, greet them warmly.
                    - Directly ask the user to choose their primary task:
                        1.  **Document Reconciliation**
                        2.  **Analyze/Query Existing Documents**
                    - *Always fetch `list_remote_agents` initially to discover available agent cards and their capabilities. Base workflow decisions on these skills when needed.*

                    **Path 1: Document Reconciliation:**
                    - If the user chooses **Document Reconciliation**:
                        - Ask them if they want to use **existing files** already in the system or if they need to **upload new documents** first.
                        -   **Sub-Path 1.A: Using Existing Files for Reconciliation:**
                            -   Ask the user for the **Purchase Order (PO) number** for the reconciliation.
                            -   Then, initiate the reconciliation workflow using `initiate_reconciliation_workflow` with the provided PO number.
                        -   **Sub-Path 1.B: Uploading New Files for Reconciliation:**
                            -   Ask the user to provide the **file path** and **document type** (either 'invoice' or 'purchase_order') for each document they want to upload for reconciliation.
                            -   For each file, use the `initiate_document_ingestion_workflow`.
                            -   During or after ingestion, try to remember/confirm the **PO number** (if a PO was ingested or an invoice references one) and the **invoice number** (if an invoice was ingested).
                            -   After both an invoice and its related PO (or the PO number itself) are ingested and identifiable, confirm with the user if they want to proceed with reconciliation using the identified PO number.
                            -   If they confirm, use `initiate_reconciliation_workflow`.
                            -   If only one document is uploaded, or if they don't want to reconcile immediately, acknowledge the ingestion and inform them the document is stored. They can choose to reconcile or analyze later.

                    **Path 2: Analyze/Query Existing Documents:**
                    - If the user chooses **Analyze/Query Existing Documents**, or if their initial message clearly indicates a query (e.g., "How many invoices from ACME Corp?", "What's the total for POs last month?"):
                        - Confirm their intent to query the database if it wasn't explicit.
                        - Use the `initiate_analyst_query_workflow` with their natural language query.
                        - The Analyst Agent will handle clarifications (like document type or specific dates) internally if needed.
                        - Present the results from the Analyst Agent clearly.

                    **General Workflow Principles:**
                    - **Agent Discovery:** Remember to always use `list_remote_agents` at the start of an interaction or if you need to re-verify agent capabilities, especially before initiating any workflow.
                    - **Workflow Preference:** Prioritize using the dedicated workflow tools (`initiate_document_ingestion_workflow`, `initiate_reconciliation_workflow`, `initiate_analyst_query_workflow`) for their respective tasks.
                    - **Fallback Interaction:** If the user's request doesn't fit a defined workflow, or if they are having a general conversation, you may use `send_message` for direct interaction with an appropriate agent (if one has been selected or is relevant). However, steer towards workflows when applicable.
                    - **State Management:**
                        - If a workflow is in progress, continue guiding the user through it until completion or an explicit stop.
                        - Keep track of key information gathered (like PO numbers, ingested document details) to facilitate multi-step processes.
                        - Always report the outcome of workflows or any errors encountered in a user-friendly manner.
                    - **Clarity:** If the user's intent is unclear, ask clarifying questions before committing to a workflow.

                    **Available Specialist Agents (discovered via `list_remote_agents` and used by workflow tools):**
                    {self.agents}

                    **Current agent (if `send_message` was used previously in this session):** {current_agent_state['active_agent']} """



    def check_state(self, context: ReadonlyContext): # No changes needed
        state = context.state
        if (
            'context_id' in state
            and 'session_active' in state
            # and state['session_active']
            and 'agent' in state
        ):
            return {'active_agent': f'{state["agent"]}'}
        return {'active_agent': 'None'}

    def before_model_callback( # No changes needed
        self, callback_context: CallbackContext, llm_request
    ):
        state = callback_context.state
        # if 'session_active' not in state or not state['session_active']:
        #     state['session_active'] = True

    async def list_remote_agents(self):
        """List the available remote agents you can use to delegate the task."""
        await self._ensure_initialized() # Ensure connections are made

        if not self.cards:
            return []

        remote_agent_info_list = []
        for card_val in self.cards.values():
            remote_agent_info_list.append(
                {'name': card_val.name, 'description': card_val.description}
            )
        return remote_agent_info_list

    async def send_message(
        self, agent_name: str, message: str, tool_context: ToolContext
    ):
        """Sends a task either streaming (if supported) or non-streaming.
        ... (rest of docstring as in original) ...
        """
        await self._ensure_initialized() # Ensure connections are made

        if agent_name not in self.remote_agent_connections:
            available_agents = list(self.remote_agent_connections.keys())
            raise ValueError(
                f'Agent "{agent_name}" not found. Available agents: {available_agents}'
            )
        
        state = tool_context.state
        state['agent'] = agent_name
        
        client_connection = self.remote_agent_connections[agent_name]
        # This check might be redundant if the key's presence guarantees a valid object,
        # but kept for safety.
        if not client_connection: 
            raise ValueError(f'Client connection not available for {agent_name}')

        task_id_val = state.get('task_id', None)
        context_id_val = state.get('context_id', None)
        message_id_val = state.get('message_id', str(uuid.uuid4()))
        state['message_id'] = message_id_val # Store it back in case it was generated

        request_params = MessageSendParams(
            id=str(uuid.uuid4()), # ID for this specific send operation
            message=Message(
                role='user',
                parts=[TextPart(text=message)],
                messageId=message_id_val,
                contextId=context_id_val,
                taskId=task_id_val,
            ),
            configuration=MessageSendConfiguration(
                acceptedOutputModes=['text', 'text/plain', 'image/png'],
            ),
        )
        
        response_from_client = await client_connection.send_message(request_params)
        
        if isinstance(response_from_client, Message):
            return await convert_parts(response_from_client.parts, tool_context)
        
        task_obj: Task = response_from_client 


        if task_obj.status.state == TaskState.input_required:
            tool_context.actions.skip_summarization = True
            tool_context.actions.escalate = True
        elif task_obj.status.state == TaskState.canceled:
            raise ValueError(f'Agent {agent_name} task {task_obj.id} was cancelled.')
        elif task_obj.status.state == TaskState.failed:
            fail_msg = f'Agent {agent_name} task {task_obj.id} failed.'
            # Try to append a reason from the task status message
            if task_obj.status and task_obj.status.message and task_obj.status.message.parts:
                for part_item in task_obj.status.message.parts:
                    if hasattr(part_item, 'root') and isinstance(part_item.root, TextPart):
                        fail_msg += f" Reason: {part_item.root.text}"
                        break 
            raise ValueError(fail_msg)
        
        # Collect and convert parts from task status message and artifacts
        converted_response_parts = []
        if task_obj.status.message and task_obj.status.message.parts:
            converted_response_parts.extend(
                await convert_parts(task_obj.status.message.parts, tool_context)
            )
        if task_obj.artifacts:
            for artifact in task_obj.artifacts:
                if artifact.parts: # Ensure artifact itself has parts
                    converted_response_parts.extend(
                        await convert_parts(artifact.parts, tool_context)
                    )
        return converted_response_parts


# Helper functions (convert_parts, convert_part) are assumed to be mostly correct.
# Added minor defensive checks to convert_part.
async def convert_parts(parts: list[Part], tool_context: ToolContext) -> list:
    rval = []
    for p_item in parts:
        rval.append(await convert_part(p_item, tool_context))
    return rval


async def convert_part(part: Part, tool_context: ToolContext):
    # Check for the expected structure Part -> root -> kind/data/file
    if hasattr(part, 'root') and part.root is not None:
        root = part.root
        if hasattr(root, 'kind'):
            if root.kind == 'text':
                return root.text
            elif root.kind == 'data':
                return root.data
            elif root.kind == 'file' and hasattr(root, 'file'):
                file_id = root.file.name
                file_bytes = base64.b64decode(root.file.bytes)
                # Ensure google.genai.types.Part and Blob are used correctly
                genai_file_part = types.Part( 
                    inline_data=types.Blob(
                        mime_type=root.file.mimeType, data=file_bytes
                    )
                )
                await tool_context.save_artifact(file_id, genai_file_part)
                tool_context.actions.skip_summarization = True
                tool_context.actions.escalate = True
                # Ensure DataPart is correctly imported or defined
                return DataPart(data={'artifact-file-id': file_id})
            else:
                return f'Unknown or malformed part root kind: {root.kind if hasattr(root, "kind") else "N/A"}'
        else:
            return 'Part root does not have a kind attribute.'
    else: # Fallback or if 'Part' has 'kind' directly (less likely based on usage)
        if hasattr(part, 'kind'):
            return f'Unknown part type (direct kind): {part.kind}'
        return 'Unknown or malformed part structure.'