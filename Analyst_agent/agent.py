import os
import json
from typing import Dict, Any, Optional, List, AsyncIterable
import traceback

from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as google_types

from dotenv import load_dotenv

load_dotenv()

import sys
project_root_db_agent = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root_db_agent not in sys.path:
    sys.path.insert(0, project_root_db_agent)

try:
    from database_manager import (
        get_documents_count_by_date_range,
        get_documents_count_by_vendor,
        get_total_amount_by_vendor,
        get_documents_by_vendor,
        get_documents_by_date_range,
        initialize_database
    )
except ImportError as e:
    print(f"ERROR (AnalystAgent): Could not import database_manager functions: {e}")
    def get_documents_count_by_date_range(*args, **kwargs): return {"error": f"database_manager not available: {e}"}
    def get_documents_count_by_vendor(*args, **kwargs): return {"error": f"database_manager not available: {e}"}
    def get_total_amount_by_vendor(*args, **kwargs): return {"error": f"database_manager not available: {e}"}
    def get_documents_by_vendor(*args, **kwargs): return {"error": f"database_manager not available: {e}"}
    def get_documents_by_date_range(*args, **kwargs): return {"error": f"database_manager not available: {e}"}
    def initialize_database(): print("Warning: initialize_database (dummy) called as import failed.")


def _get_doc_count_date_range_tool(document_type: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """
    TOOL: Gets the count of documents (invoices or purchase_orders) within a specified date range.
    Dates should be in YYYY-MM-DD format.
    document_type must be 'invoice' or 'purchase_order'.
    """
    normalized_doc_type = str(document_type).strip().lower().replace(" ", "_")
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return {"status": "error", "message": "Invalid document_type. Must be 'invoice' or 'purchase_order'."}
    try:
        count = get_documents_count_by_date_range(normalized_doc_type, start_date, end_date)
        return {"status": "success", "document_type": normalized_doc_type, "start_date": start_date, "end_date": end_date, "count": count}
    except Exception as e:
        print(f"ERROR in _get_doc_count_date_range_tool: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": f"Error querying database for date range count: {str(e)}"}

def _get_doc_count_vendor_tool(document_type: str, vendor_name: str) -> Dict[str, Any]:
    """
    TOOL: Gets the count of documents (invoices or purchase_orders) for a specific vendor name.
    document_type must be 'invoice' or 'purchase_order'.
    """
    normalized_doc_type = str(document_type).strip().lower().replace(" ", "_")
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return {"status": "error", "message": "Invalid document_type. Must be 'invoice' or 'purchase_order'."}
    try:
        count = get_documents_count_by_vendor(normalized_doc_type, vendor_name)
        return {"status": "success", "document_type": normalized_doc_type, "vendor_name": vendor_name, "count": count}
    except Exception as e:
        print(f"ERROR in _get_doc_count_vendor_tool: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": f"Error querying database for vendor count: {str(e)}"}

def _get_total_amount_vendor_tool(document_type: str, vendor_name: str) -> Dict[str, Any]:
    """
    TOOL: Gets the total amount of documents (invoices or purchase_orders) for a specific vendor name.
    document_type must be 'invoice' or 'purchase_order'.
    """
    normalized_doc_type = str(document_type).strip().lower().replace(" ", "_")
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return {"status": "error", "message": "Invalid document_type. Must be 'invoice' or 'purchase_order'."}
    try:
        total_amount = get_total_amount_by_vendor(normalized_doc_type, vendor_name)
        if total_amount is None:
             return {"status": "success", "document_type": normalized_doc_type, "vendor_name": vendor_name, "total_amount": "N/A (No data found or non-numeric)"}
        return {"status": "success", "document_type": normalized_doc_type, "vendor_name": vendor_name, "total_amount": f"{float(total_amount):.2f}"}
    except Exception as e:
        print(f"ERROR in _get_total_amount_vendor_tool: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": f"Error querying database for vendor total amount: {str(e)}"}

def _list_documents_vendor_tool(document_type: str, vendor_name: str, limit: int = 5) -> Dict[str, Any]:
    """
    TOOL: Lists documents (invoices or purchase_orders) for a specific vendor name, up to a limit.
    document_type must be 'invoice' or 'purchase_order'.
    """
    normalized_doc_type = str(document_type).strip().lower().replace(" ", "_")
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return {"status": "error", "message": "Invalid document_type. Must be 'invoice' or 'purchase_order'."}
    try:
        safe_limit = max(1, int(limit)) if isinstance(limit, (int, float, str)) and str(limit).isdigit() else 5
        documents = get_documents_by_vendor(normalized_doc_type, vendor_name, safe_limit) # Pass safe_limit
        if not isinstance(documents, list):
            return {"status": "error", "message": f"Database function get_documents_by_vendor did not return a list for {normalized_doc_type} by {vendor_name}."}
        return {"status": "success", "document_type": normalized_doc_type, "vendor_name": vendor_name, "documents_found": len(documents), "documents_preview": documents} # Return all found up to limit
    except Exception as e:
        print(f"ERROR in _list_documents_vendor_tool: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": f"Error querying database for vendor document list: {str(e)}"}

def _list_documents_date_range_tool(document_type: str, start_date: str, end_date: str, limit: int = 5) -> Dict[str, Any]:
    """
    TOOL: Lists documents (invoices or purchase_orders) within a date range, up to a limit.
    Dates should be in YYYY-MM-DD format.
    document_type must be 'invoice' or 'purchase_order'.
    """
    normalized_doc_type = str(document_type).strip().lower().replace(" ", "_")
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return {"status": "error", "message": "Invalid document_type. Must be 'invoice' or 'purchase_order'."}
    try:
        safe_limit = max(1, int(limit)) if isinstance(limit, (int, float, str)) and str(limit).isdigit() else 5
        documents = get_documents_by_date_range(normalized_doc_type, start_date, end_date, safe_limit) # Pass safe_limit
        if not isinstance(documents, list):
            return {"status": "error", "message": f"Database function get_documents_by_date_range did not return a list for {normalized_doc_type} between {start_date}-{end_date}."}
        return {"status": "success", "document_type": normalized_doc_type, "start_date": start_date, "end_date": end_date, "documents_found": len(documents), "documents_preview": documents} # Return all found up to limit
    except Exception as e:
        print(f"ERROR in _list_documents_date_range_tool: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": f"Error querying database for date range document list: {str(e)}"}

class AnalystAgent:
    DB_QUERY_AGENT_NAME = "database_analyst_agent"
    DB_QUERY_AGENT_DESCRIPTION = "Agent to query invoice and purchase order database, providing insights and summaries to users."

    def __init__(self, user_id: str = "analyst_service_user"):
        self._agent = self._build_agent()
        self._user_id = user_id
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
        if not os.getenv("GOOGLE_API_KEY"):
            print("AnalystAgent Warning: GOOGLE_API_KEY is not set. Agent calls will likely fail.")

    def _build_agent(self) -> LlmAgent:
        return LlmAgent(
            name=self.DB_QUERY_AGENT_NAME,
            model=os.getenv("ADK_MODEL", "gemini-1.5-flash-latest"),
            description=self.DB_QUERY_AGENT_DESCRIPTION,
            instruction=(
                "You are a helpful Database Analyst Assistant. Your primary role is to assist users in retrieving information about invoices and purchase orders from a financial database. "
                "You have access to several tools to query this database. Your goal is to understand the user's request, select the most appropriate tool, and present the information clearly.\n\n"
                "**Interaction Flow:**\n"
                "1.  **Clarification is Key:** If a user's request is ambiguous, especially regarding `document_type` ('invoice' or 'purchase_order') or date formats, YOU MUST ASK for clarification. For dates, always request `YYYY-MM-DD` format if the user provides vague terms (e.g., 'last month', 'this year', 'January'). If a date range tool is chosen and only one date is provided, ask for the other date (start or end) to complete the range.\n"
                "2.  **Tool Selection:** Based on the clarified request, choose the best tool from the list below. Only use one tool per turn unless the user explicitly asks for multiple distinct pieces of information that require different tools sequentially.\n"
                "3.  **Parameter Extraction:** Accurately extract all necessary parameters for the chosen tool from the user's message and your prior conversation history if relevant (e.g. if document_type was clarified earlier).\n"
                "4.  **Tool Execution:** Call the selected tool with the extracted parameters.\n"
                "5.  **Presenting Results:**\n"
                "    *   If the tool call is successful (`status: 'success'`): Clearly summarize the results in a user-friendly way. For example, instead of just raw JSON, say 'I found X invoices for Vendor Y.' or 'The total amount for POs from Vendor Z is $ABC.' For lists, mention how many were found and show the preview. When showing a preview from `_list_documents_vendor_tool` or `_list_documents_date_range_tool`, format the 'documents_preview' list into a readable, bulleted list or a small table if appropriate. Each item in the preview is a dictionary; present key fields like 'document_number', 'date', 'total_amount'.\n"
                "    *   If the tool call results in an error (`status: 'error'`): Inform the user that there was an issue and state the error message from the tool output. Do not try to guess or make up data.\n"
                "    *   If the tool returns a count of 0 or no documents, state that clearly, e.g., 'No invoices were found for Vendor X in that period.'\n"
                "6.  **Follow-up:** After presenting results, you can ask if the user needs further assistance or more details (e.g., 'Would you like to see a list of these documents if you haven't already?').\n\n"
                "**Available Tools (and their required parameters):\n"
                "   - `_get_doc_count_date_range_tool`: Gets count of documents. Requires: `document_type` (string: 'invoice' or 'purchase_order'), `start_date` (string: YYYY-MM-DD), `end_date` (string: YYYY-MM-DD).\n"
                "   - `_get_doc_count_vendor_tool`: Gets count of documents for a vendor. Requires: `document_type` (string: 'invoice' or 'purchase_order'), `vendor_name` (string).\n"
                "   - `_get_total_amount_vendor_tool`: Gets total monetary amount for a vendor. Requires: `document_type` (string: 'invoice' or 'purchase_order'), `vendor_name` (string).\n"
                "   - `_list_documents_vendor_tool`: Lists some documents for a vendor. Requires: `document_type` (string: 'invoice' or 'purchase_order'), `vendor_name` (string). Optional: `limit` (integer, default 5).\n"
                "   - `_list_documents_date_range_tool`: Lists some documents in a date range. Requires: `document_type` (string: 'invoice' or 'purchase_order'), `start_date` (string: YYYY-MM-DD), `end_date` (string: YYYY-MM-DD). Optional: `limit` (integer, default 5).\n\n"
                "**Important Considerations:**\n"
                "- If a user asks a general question like 'Tell me about invoices from Acme Corp', a good first step might be to use `_get_doc_count_vendor_tool` or `_get_total_amount_vendor_tool`. Then, based on the result or user follow-up, you can offer to use `_list_documents_vendor_tool`.\n"
                "- Be polite and professional. Your responses should be conversational but focused on providing the requested data or guiding the user to provide necessary information.\n"
                "- Do not perform calculations yourself beyond what the tools provide. Rely on the tool outputs.\n"
                "- If you are unsure which tool to use or if the request is too complex for your tools, state that you cannot fulfill the request as is and suggest how the user might rephrase or simplify it."
            ),
            tools=[
                _get_doc_count_date_range_tool,
                _get_doc_count_vendor_tool,
                _get_total_amount_vendor_tool,
                _list_documents_vendor_tool,
                _list_documents_date_range_tool
            ]
        )

    def get_processing_message(self) -> str:
        return "Analyst Agent is querying the database..."

    async def query(self, user_query: str, session_id: Optional[str] = None) -> AsyncIterable[dict[str, Any]]:
        if not user_query or not user_query.strip():
            yield {
                'is_task_complete': True,
                'content': "I need a query to process. Please tell me what information you're looking for.",
                'session_id': session_id
            }
            return

        current_session_id = session_id
        session = None

        if current_session_id:
            session = await self._runner.session_service.get_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=current_session_id,
            )
        
        if not session:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=current_session_id if current_session_id else None
            )
        
        current_session_id = session.id

        content = google_types.Content(
            role='user', parts=[google_types.Part.from_text(text=user_query)]
        )

        if not os.getenv("GOOGLE_API_KEY"):
            yield {
                'is_task_complete': True,
                'content': "I'm unable to process your request right now due to a configuration issue (missing API key). Please try again later.",
                'session_id': current_session_id
            }
            return

        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=current_session_id, new_message=content
        ):
            response_content = ""
            is_tool_call_related = False

            if event.content and event.content.parts:
                if any(p.function_call for p in event.content.parts):
                    is_tool_call_related = True
                    response_content = self.get_processing_message()
                elif any(p.function_response for p in event.content.parts):
                    is_tool_call_related = True
                    text_parts = [p.text for p in event.content.parts if p.text]
                    if text_parts:
                        response_content = "\n".join(text_parts).strip()
                    else:
                        response_content = "Processing tool results..."
                else:
                    response_content = "\n".join(
                        [p.text for p in event.content.parts if p.text]
                    ).strip()

            if event.is_final_response():
                final_text = response_content if response_content else "No further information from the agent."
                yield {
                    'is_task_complete': True,
                    'content': final_text,
                    'session_id': current_session_id
                }
                return
            else:
                yield {
                    'is_task_complete': False,
                    'updates': response_content if response_content else (self.get_processing_message() if is_tool_call_related else "Analyst Agent is thinking..."),
                    'session_id': current_session_id
                }
    async def stream(self, query: str, session_id: str) -> AsyncIterable[dict[str, Any]]:
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )
        content = google_types.Content(
            role='user', parts=[google_types.Part.from_text(text=query)]
        )
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )
        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=session.id, new_message=content
        ):
            if event.is_final_response():
                response: Any = ''
                if (
                    event.content
                    and event.content.parts
                    and event.content.parts[0].text
                ):
                    response = '\n'.join(
                        [p.text for p in event.content.parts if p.text]
                    )
                elif (
                    event.content
                    and event.content.parts
                    and any(
                        p.function_response for p in event.content.parts
                    )
                ):
                    response = next(
                        p.function_response.model_dump()
                        for p in event.content.parts if p.function_response
                    )
                yield {
                    'is_task_complete': True,
                    'content': response,
                }
            else:
                yield {
                    'is_task_complete': False,
                    'updates': self.get_processing_message(),
                }

