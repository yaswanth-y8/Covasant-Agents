import os
import json
from typing import Dict, Any, Optional, AsyncIterable
import traceback
import re
from difflib import SequenceMatcher

from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as google_types
from dotenv import load_dotenv

load_dotenv()

import sys
project_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir)

try:
    from database_manager import get_invoice_by_related_po, get_po_by_number
except ImportError:
    # Fallback if database_manager is not found, agent will error out if DB access is needed.
    def get_invoice_by_number(doc_number: str) -> Optional[dict]:
        raise ImportError("database_manager.get_invoice_by_number not available")
    def get_po_by_number(doc_number: str) -> Optional[dict]:
        raise ImportError("database_manager.get_po_by_number not available")


class ReconciliationAgent:

    def __init__(self, user_id: str = "reconciliation_service_user"):
        self._agent = self._build_agent()
        self._user_id = user_id
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    @staticmethod
    def _compare_strings_fuzzy_local(s1: Optional[str], s2: Optional[str], threshold=0.8) -> bool:
        if s1 is None and s2 is None: return True
        if s1 is None or s2 is None: return False
        clean_s1 = re.sub(r'[^\w\s]', '', str(s1).lower().strip())
        clean_s2 = re.sub(r'[^\w\s]', '', str(s2).lower().strip())
        if not clean_s1 and not clean_s2: return True
        if not clean_s1 or not clean_s2: return False
        return SequenceMatcher(None, clean_s1, clean_s2).ratio() >= threshold

    @staticmethod
    def _compare_amounts_local(amount1: Any, amount2: Any, tolerance=0.01) -> bool:
        try:
            amt1_str = str(amount1) if amount1 is not None else "0.0"
            amt2_str = str(amount2) if amount2 is not None else "0.0"
            amt1 = float(amt1_str.replace(',', ''))
            amt2 = float(amt2_str.replace(',', ''))
            return abs(amt1 - amt2) <= tolerance
        except (ValueError, TypeError):
            return False

    def _internal_reconciliation_logic(self, invoice_extraction_data: dict, po_extraction_data: dict) -> dict:
        try:
            if not isinstance(invoice_extraction_data, dict) or invoice_extraction_data.get("status") != "success" or "data" not in invoice_extraction_data:
                return {"status": "error", "error_message": f"Invoice data for reconciliation is not valid or missing 'data' (status: {invoice_extraction_data.get('status')})."}
            if not isinstance(po_extraction_data, dict) or po_extraction_data.get("status") != "success" or "data" not in po_extraction_data:
                return {"status": "error", "error_message": f"PO data for reconciliation is not valid or missing 'data' (status: {po_extraction_data.get('status')})."}

            invoice_data = invoice_extraction_data.get("data", {})
            po_data = po_extraction_data.get("data", {})

            discrepancies = []
            matched_fields = []

            actual_po_num_raw = po_data.get("document_number")
            actual_po_num = str(actual_po_num_raw).strip().upper() if actual_po_num_raw and isinstance(actual_po_num_raw, (str, int, float)) else None

            inv_vendor = invoice_data.get("vendor_name")
            po_vendor = po_data.get("vendor_name")
            if self._compare_strings_fuzzy_local(inv_vendor, po_vendor):
                matched_fields.append("vendor_name")
            else:
                discrepancies.append(f"Vendor Mismatch: Invoice='{inv_vendor or 'N/A'}' vs PO='{po_vendor or 'N/A'}'")

            inv_amount = invoice_data.get("total_amount")
            po_amount = po_data.get("total_amount")
            if self._compare_amounts_local(inv_amount, po_amount):
                matched_fields.append("total_amount")
            else:
                discrepancies.append(f"Total Amount Mismatch: Invoice=${float(str(inv_amount).replace(',','') or 0):.2f} vs PO=${float(str(po_amount).replace(',','') or 0):.2f}")

            inv_items = invoice_data.get("line_items", [])
            po_items = po_data.get("line_items", [])
            if not isinstance(inv_items, list): inv_items = []
            if not isinstance(po_items, list): po_items = []

            if len(inv_items) == len(po_items):
                if len(inv_items) > 0 or (len(inv_items)==0 and len(po_items)==0):
                     matched_fields.append("line_items_count")
            else:
                discrepancies.append(f"Line Item Count Mismatch: Invoice={len(inv_items)} vs PO={len(po_items)}")

            key_fields_considered = ["vendor_name", "total_amount"]
            if (inv_items or po_items):
                key_fields_considered.append("line_items_count")

            num_matched_key_fields = sum(1 for f in matched_fields if f in key_fields_considered)
            total_key_fields_for_calc = len(key_fields_considered)
            match_percentage = (num_matched_key_fields / total_key_fields_for_calc * 100) if total_key_fields_for_calc > 0 else 0

            status_reco = "REJECTED"
            if not discrepancies and actual_po_num:
                status_reco = "APPROVED"
            elif "PO Number Mismatch on Invoice" in ' '.join(discrepancies) or "Critical: PO number missing" in ' '.join(discrepancies) or not actual_po_num:
                status_reco = "REJECTED"
            elif match_percentage >= 75 and discrepancies:
                status_reco = "NEEDS_REVIEW"
            elif discrepancies:
                status_reco = "REJECTED"

            recommendation = "Default recommendation: Review details."
            if status_reco == "APPROVED": recommendation = "Invoice and PO appear to match on key fields."
            elif status_reco == "REJECTED": recommendation = "Significant discrepancies or critical mismatch found (e.g., PO numbers). Manual investigation required."
            elif status_reco == "NEEDS_REVIEW": recommendation = f"High match ({match_percentage:.1f}%) but with discrepancies. Manual review recommended."

            inv_conf = float(invoice_extraction_data.get("confidence_score", 0.5))
            po_conf = float(po_extraction_data.get("confidence_score", 0.5))
            avg_doc_confidence = (inv_conf + po_conf) / 2
            overall_confidence_score = (avg_doc_confidence * 0.4) + ((match_percentage / 100) * 0.6)

            return {
                "status": "success",
                "reconciliation_result": {
                    "approval_status": status_reco,
                    "match_percentage": round(match_percentage, 1),
                    "reconciliation_confidence_score": round(overall_confidence_score, 2),
                    "matched_fields": matched_fields,
                    "discrepancies": discrepancies,
                    "recommendation": recommendation,
                    "summary": {
                        "invoice_number": invoice_data.get("document_number", "N/A"),
                        "po_number_from_po_data": actual_po_num or "N/A",
                        "invoice_total": inv_amount if inv_amount is not None else "N/A",
                        "po_total": po_amount if po_amount is not None else "N/A",
                        "invoice_vendor": inv_vendor or "N/A",
                        "po_vendor": po_vendor or "N/A"
                    }
                }
            }
           
        except Exception as e:
            # This print is for critical, unexpected errors within the tool's logic.
            print(f"ERROR in _internal_reconciliation_logic (General Exception): {e}\n{traceback.format_exc()}")
            return {"status": "error", "error_message": f"Reconciliation logic error: {str(e)}"}

    def _fetch_and_reconcile_documents_tool(self, po_number: str) -> dict:
        """
        TOOL for ReconciliationAgent: Fetches invoice and PO data from the database
        using their numbers, then performs reconciliation.
        """
        try:
            invoice_doc_full = get_invoice_by_related_po(po_number)
            po_doc_full = get_po_by_number(po_number)
            if not invoice_doc_full:
                return {"status": "error", "error_message": f"Invoice with '{po_number}' not found in database."}
            if not po_doc_full:
                return {"status": "error", "error_message": f"Purchase Order '{po_number}' not found in database."}

            return self._internal_reconciliation_logic(invoice_doc_full, po_doc_full)
        except ImportError as ie: # Catch if database_manager functions were not loaded
            print(f"ERROR in _fetch_and_reconcile_documents_tool (ImportError): {ie}\n{traceback.format_exc()}")
            return {"status": "error", "error_message": f"Database access error: {str(ie)}"}
        except Exception as e:
            # This print is for critical, unexpected errors within the tool's logic.
            print(f"ERROR in _fetch_and_reconcile_documents_tool (General Exception): {e}\n{traceback.format_exc()}")
            return {"status": "error", "error_message": f"Error fetching or preparing data for reconciliation: {str(e)}"}


    def _build_agent(self) -> LlmAgent:
        agent_name = "reconciliation_specialist_agent"
        return LlmAgent(
            name=agent_name,
            model=os.getenv("ADK_MODEL", "gemini-1.5-flash-latest"),
            description="Specialized agent for fetching purchase order data and its related invoice data from a database using the purchase order number, comparing them, and determining a reconciliation status.", # Refined description
            instruction=(
                "You are a Reconciliation Specialist. Your ONLY task is to reconcile an invoice and a purchase order using the provided Purchase Order (PO) number.\n"
                "1. You will be given a `po_number` by the user/orchestrator in their message. You MUST extract this `po_number`.\n" # Simplified
                "2. Use your `_fetch_and_reconcile_documents_tool` ONLY with this extracted `po_number`. The tool will find the related invoice using this PO number.\n" # Clarified
                "3. After the tool executes, you MUST return the complete JSON result from the tool directly as your response. Do not add any conversational fluff, explanations, or attempt further actions or tool calls.\n" # Stronger instruction to stop
                "If the `po_number` is unclear or missing from the user message, you MUST return an error JSON: {\"status\": \"error\", \"error_message\": \"PO number was not clearly provided or is missing in the user message.\"}. Do not ask for clarification." # Added specific error handling instruction
            ),
            tools=[
                self._fetch_and_reconcile_documents_tool
            ]
    )

    def get_processing_message(self) -> str:
        return "Reconciliation Agent is fetching and comparing the documents..."

    async def reconcile_documents(self ,po_number: str, session_id: Optional[str] = None) -> AsyncIterable[dict[str, Any]]:
        user_message_text = (
            f"Please reconcile the documents.\n"
            f"Purchase Order Number: \"{po_number}\""
        )

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
                    session_id=current_session_id
                )
        
        if not session:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id
            )
        
        current_session_id = session.id

        content = google_types.Content(
            role='user', parts=[google_types.Part.from_text(text=user_message_text)]
        )

        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=current_session_id, new_message=content
        ):
            if event.is_final_response():
                final_response_data = None
                if event.content and event.content.parts:
                    final_text_response = event.content.parts[0].text if event.content.parts[0].text else ""
                    if final_text_response:
                        try:
                            final_response_data = json.loads(final_text_response)
                        except json.JSONDecodeError:
                            final_response_data = {"status": "error", "error_message": "LLM did not return valid JSON.", "raw_response": final_text_response}
                    else:
                        final_response_data = {"status": "error", "error_message": "LLM final response was empty."}
                else:
                    final_response_data = {"status": "error", "error_message": "LLM final response had no content structure."}
                
                yield {
                    'is_task_complete': True,
                    'content': final_response_data,
                    'session_id': current_session_id
                }
                return
            else:
                update_text = ""
                if event.content and event.content.parts:
                    update_text = '\n'.join(
                        [p.text for p in event.content.parts if p.text]
                    ).strip()
                yield {
                    'is_task_complete': False,
                    'updates': update_text if update_text else self.get_processing_message(),
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
