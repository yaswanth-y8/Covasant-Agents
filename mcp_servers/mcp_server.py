from mcp.server.fastmcp import FastMCP
import os
import json
from typing import Dict, Any, Optional, List, AsyncIterable
import traceback


mcp=FastMCP()

from Agents.database_manager import (
        get_documents_count_by_date_range,
        get_documents_count_by_vendor,
        get_total_amount_by_vendor,
        get_documents_by_vendor,
        get_documents_by_date_range,
        initialize_database
    )

@mcp.tool()
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
@mcp.tool()
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
@mcp.tool()
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
@mcp.tool()
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
@mcp.tool()
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

if __name__=="__main__":
    mcp.run(transport="sse")