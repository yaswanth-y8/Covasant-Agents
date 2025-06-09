"""
Data Ingestion Agent for processing and storing financial documents.

This agent uses an MCP Toolset to interact with document parsing and
database storage capabilities provided by a separate MCP server.
"""
import os
import json
from typing import Any, AsyncIterable, Optional

from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset,SseServerParams
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    print("CRITICAL WARNING: GOOGLE_API_KEY not set. LLM  will fail.")


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
        if not os.getenv("GOOGLE_API_KEY"):
            print("Warning: GOOGLE_API_KEY is not set. Agent calls will likely fail.")

    def _build_agent(self) -> LlmAgent:
        """Builds the LLM agent for data ingestion."""
        agent_name = "data_ingestion_specialist_agent"
        return LlmAgent(
            name=agent_name,
            model=os.getenv("ADK_MODEL", "gemini-1.5-flash-latest"),
            description="Specialized agent for processing raw documents (invoices, POs), " \
            "extracting their data using advanced parsing, and storing them into the database.",
            instruction=(
                "You are a Data Ingestion Specialist,"\
                    "Your ONLY task is to process a single document file.\n"
                "1. You will be given a `raw_document_file_path` and"\
                 " a `document_type` ('invoice' or 'purchase_order') by the user/orchestrator.\n"
                "2. Use your `_ingest_and_store_document_tool` with these arguments,"
                " which you must extract from the user's message.\n"
                "3. Return the complete JSON result from the tool directly back as your response."\
                    "Do not add any conversational fluff or explanations around the JSON.\n"
                "Do NOT ask clarifying questions. Execute the tool with the provided arguments immediately."
                "If the file path or document type is unclear from the user message, "
                "you should indicate an error rather than ask for clarification."
            ),
            tools=[MCPToolset(connection_params=SseServerParams(url="http://127.0.0.1:8000/sse"))],
            output_key="ingestion_state"
        )

    def get_processing_message(self) -> str:
        """Returns a generic processing message."""
        return "Data Ingestion Agent is processing the document..."
    async def ingest_document(self, raw_document_file_path: str,
                               document_type: str,
                                 session_id: Optional[str] = None) -> AsyncIterable[dict[str, Any]]:
        """
        Processes a document by providing its path and type to the agent.
        Yields events from the agent interaction, with the final event containing the result.

        Args:
            raw_document_file_path: The absolute or relative path to the document file.
            document_type: The type of the document (e.g., "invoice", "purchase_order").
            session_id: Optional existing session ID to continue a session.

        Yields:
            Dictionaries representing events from the agent interaction.
            The final event includes `is_task_complete: True` and `content` 
            (the parsed JSON result from the tool).
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

        content = types.Content(
            role='user', parts=[types.Part.from_text(text=user_message_text)]
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
                            print(f"Warning: Final response from LLM was not valid JSON as instructed. Response: '{final_text_response}'")
                            final_response_data = {"status": "error", 
                                                   "error_message": "LLM did not return valid JSON.", 
                                                   "raw_response": final_text_response}
                    else:
                        final_response_data = {"status": "error", "error_message": "LLM final response was empty."}
                else:
                    final_response_data = {"status": "error",
                                            "error_message": "LLM final response had no content structure."}
                
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

    async def stream(self, query, session_id) -> AsyncIterable[dict[str, Any]]:
        """
        Provides a generic streaming interface to the agent.
        The user_query should contain enough context for the agent to act.
        """
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
                    and any(p.function_response for p in event.content.parts)
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
    def get_agent(self):
        """Returns the underlying LLM agent instance."""
        return self._build_agent()

root_agent=DataIngestionAgent().get_agent()
