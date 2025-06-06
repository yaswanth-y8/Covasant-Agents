import os
import json
from typing import Dict, Any, AsyncIterable, Optional

from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project root setup for relative imports
import sys

project_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir)

from Data_ingestion_agent.document_parser import process_raw_document_to_json
from database_manager import store_invoice_data, store_po_data


# Critical API key check
if not os.getenv("GOOGLE_API_KEY"):
    print("CRITICAL WARNING (DataIngestionAgentWrapper): GOOGLE_API_KEY not set. LLM functionalities will fail.")


class DataIngestionAgent:
    """
    A  class for the Data Ingestion Specialist Agent.
    This agent processes document files, extracts data, and stores it.
    """

    def __init__(self, user_id: str = "data_ingestion_service_user"):
        """
        Initializes the DataIngestionAgentWrapper.

        Args:
            user_id: An identifier for the user interacting with the agent.
        """
        self._agent = self._build_agent()
        self._user_id = user_id
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
        if not os.getenv("GOOGLE_API_KEY"): # Re-check for emphasis during instantiation
            print("DataIngestionAgentWrapper Warning: GOOGLE_API_KEY is not set. Agent calls will likely fail.")


    def _ingest_and_store_document_tool(self, raw_document_file_path: str, document_type: str) -> dict:
        """
        TOOL for DataIngestionAgent: Extracts data from a document file and stores it.
        Returns a dictionary containing the status, message, and key extracted information.
        """
        print(f"DATA_INGESTION_TOOL: Processing file='{raw_document_file_path}', type='{document_type}'")

        if document_type.lower() not in ["invoice", "purchase_order"]:
            return {"status": "error", "error_message": "Invalid document_type. Must be 'invoice' or 'purchase_order'."}

        # Check if file exists before processing
        if not os.path.exists(raw_document_file_path):
            return {"status": "error", "error_message": f"File not found: {raw_document_file_path}"}
        if not os.path.isfile(raw_document_file_path):
            return {"status": "error", "error_message": f"Path is not a file: {raw_document_file_path}"}


        extraction_result = process_raw_document_to_json(raw_document_file_path, document_type)

        if extraction_result.get("status") != "success":
            return {
                "status": "error",
                "error_message": f"Data extraction failed: {extraction_result.get('error_message')}",
                "details": extraction_result
            }

        doc_data = extraction_result.get("data")
        if not doc_data:
            return {"status": "error", "error_message": "Extraction successful, but no 'data' field found in result."}

        doc_number_raw = doc_data.get("document_number")
        if not doc_number_raw: # Handles None, empty string, etc. after .get()
            return {"status": "error", "error_message": "Document number missing from extracted data, cannot store."}

        doc_number = str(doc_number_raw).strip().upper()
        if not doc_number: # Handles case where doc_number_raw was whitespace
            return {"status": "error", "error_message": "Document number is empty after processing."}

        stored_successfully = False
        if document_type.lower() == "invoice":
            stored_successfully = store_invoice_data(doc_number, extraction_result)
        elif document_type.lower() == "purchase_order":
            stored_successfully = store_po_data(doc_number, extraction_result)

        if stored_successfully:
            return {
                "status": "success",
                "message": f"{document_type.capitalize()} '{doc_number}' processed and stored successfully.",
                "document_number": doc_number,
                "full_extraction_result": extraction_result
            }
        else:
            return {
                "status": "error",
                "error_message": f"Failed to store {document_type} '{doc_number}' in DB.",
                "document_number": doc_number, 
                "full_extraction_result": extraction_result
            }

    def _build_agent(self) -> LlmAgent:
        """Builds the LLM agent for data ingestion."""
        agent_name = "data_ingestion_specialist_agent"
        return LlmAgent(
            name=agent_name,
            model=os.getenv("ADK_MODEL", "gemini-1.5-flash-latest"),
            description="Specialized agent for processing raw documents (invoices, POs), extracting their data using advanced parsing, and storing them into the database.",
            instruction=(
                "You are a Data Ingestion Specialist. Your ONLY task is to process a single document file.\n"
                "1. You will be given a `raw_document_file_path` and a `document_type` ('invoice' or 'purchase_order') by the user/orchestrator.\n"
                "2. Use your `_ingest_and_store_document_tool` with these arguments which you must extract from the user's message.\n"
                "3. Return the complete JSON result from the tool directly back as your response. Do not add any conversational fluff or explanations around the JSON.\n"
                "Do NOT ask clarifying questions. Execute the tool with the provided arguments immediately. If the file path or document type is unclear from the user message, you should indicate an error rather than ask for clarification."
            ),
            tools=[
                self._ingest_and_store_document_tool
            ]
        )

    def get_processing_message(self) -> str:
        """Returns a generic processing message."""
        return "Data Ingestion Agent is processing the document..."
    async def ingest_document(self, raw_document_file_path: str, document_type: str, session_id: Optional[str] = None) -> AsyncIterable[dict[str, Any]]:
        """
        Processes a document by providing its path and type to the agent.
        Yields events from the agent interaction, with the final event containing the result.

        Args:
            raw_document_file_path: The absolute or relative path to the document file.
            document_type: The type of the document (e.g., "invoice", "purchase_order").
            session_id: Optional existing session ID to continue a session.

        Yields:
            Dictionaries representing events from the agent interaction.
            The final event includes `is_task_complete: True` and `content` (the parsed JSON result from the tool).
        """
        user_message_text = (
            f"Please process and store the document.\n"
            f"File Path: \"{raw_document_file_path}\"\n"
            f"Document Type: \"{document_type}\""
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
                print(f"DataIngestionAgentWrapper: Session ID '{current_session_id}' not found. Creating a new session, trying to use this ID.")
                # Attempt to create with the provided ID, InMemorySessionService supports this.
                session = await self._runner.session_service.create_session(
                    app_name=self._agent.name,
                    user_id=self._user_id,
                    session_id=current_session_id 
                )
        
        if not session: # If no session_id was provided, or if creating with provided ID failed (shouldn't with InMemory)
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id
            )
        
        current_session_id = session.id # Use the definitive session ID from the session object

        content = types.Content(
            role='user', parts=[types.Part.from_text(text=user_message_text)]
        )

        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=current_session_id, new_message=content
        ):
            if event.is_final_response():
                final_response_data = None
                if event.content and event.content.parts:
                    # The LLM is instructed to return the JSON from the tool as its text response.
                    # The first part should contain this text.
                    final_text_response = event.content.parts[0].text if event.content.parts[0].text else ""
                    if final_text_response:
                        try:
                            final_response_data = json.loads(final_text_response)
                        except json.JSONDecodeError:
                            print(f"DataIngestionAgentWrapper Warning: Final response from LLM was not valid JSON as instructed. Response: '{final_text_response}'")
                            final_response_data = {"status": "error", "error_message": "LLM did not return valid JSON.", "raw_response": final_text_response}
                    else:
                        # This might happen if the tool call failed before LLM could respond, or LLM gave empty response.
                        final_response_data = {"status": "error", "error_message": "LLM final response was empty."}
                else:
                    final_response_data = {"status": "error", "error_message": "LLM final response had no content structure."}
                
                yield {
                    'is_task_complete': True,
                    'content': final_response_data,
                    'session_id': current_session_id
                }
                return # Stop iteration after final response
            else:
                # Non-final event, could be an update or intermediate step.
                update_text = ""
                if event.content and event.content.parts:
                    # Concatenate text from all parts for the update message
                    update_text = '\n'.join(
                        [p.text for p in event.content.parts if p.text]
                    ).strip()

                yield {
                    'is_task_complete': False,
                    'updates': update_text if update_text else self.get_processing_message(), # Provide a default if no text
                    'session_id': current_session_id
                }

    async def stream(self, query, session_id) -> AsyncIterable[dict[str, Any]]:
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )
        content = types.Content(
            role='user', parts=[types.Part.from_text(text=query)]
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
                response = ''
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
                        [
                            True
                            for p in event.content.parts
                            if p.function_response
                        ]
                    )
                ):
                    response = next(
                        p.function_response.model_dump()
                        for p in event.content.parts
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

# root_agent=DataIngestionAgent()._build_agent()