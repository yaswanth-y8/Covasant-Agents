from mcp.server.fastmcp import FastMCP
import os
import json
from typing import Dict, Any, Optional, List, AsyncIterable
import traceback
from document_parser import process_raw_document_to_json
import re
from difflib import SequenceMatcher

mcp=FastMCP()

from  database_manager import *

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
def _get_total_amount_vendor_tool(vendor_name: str,document_type: str="purchase_order") -> Dict[str, Any]:
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


@mcp.tool()
def _ingest_and_store_document_tool(raw_document_file_path: str, document_type: str) -> dict:
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
        if not doc_number_raw:
            return {"status": "error", "error_message": "Document number missing from extracted data, cannot store."}

        doc_number = str(doc_number_raw).strip().upper()
        if not doc_number: 
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



@mcp.tool()
def _get_top_vendors_by_doc_count_tool(document_type: str, limit: int = 5) -> Dict[str, Any]:
    """
    TOOL: Gets a list of top vendors based on the number of documents (invoices or purchase_orders).
    document_type must be 'invoice' or 'purchase_order'.
    limit specifies how many top vendors to return, defaults to 5.
    """
    normalized_doc_type = str(document_type).strip().lower().replace(" ", "_")
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return {"status": "error", "message": "Invalid document_type. Must be 'invoice' or 'purchase_order'."}
    try:
        safe_limit = max(1, int(limit)) if isinstance(limit, (int, float, str)) and str(limit).isdigit() else 5
        top_vendors = get_top_vendors_by_document_count(normalized_doc_type, safe_limit)
        return {"status": "success", "document_type": normalized_doc_type, "top_vendors_by_count": top_vendors}
    except Exception as e:
        print(f"ERROR in _get_top_vendors_by_doc_count_tool: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": f"Error fetching top vendors by document count: {str(e)}"}

@mcp.tool()
def _get_top_vendors_by_total_amount_tool(document_type: str, limit: int = 5) -> Dict[str, Any]:
    """
    TOOL: Gets a list of top vendors based on the total amount from their documents (invoices or purchase_orders).
    document_type must be 'invoice' or 'purchase_order'.
    limit specifies how many top vendors to return, defaults to 5.
    """
    normalized_doc_type = str(document_type).strip().lower().replace(" ", "_")
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return {"status": "error", "message": "Invalid document_type. Must be 'invoice' or 'purchase_order'."}
    try:
        safe_limit = max(1, int(limit)) if isinstance(limit, (int, float, str)) and str(limit).isdigit() else 5
        top_vendors = get_top_vendors_by_total_amount(normalized_doc_type, safe_limit)
        # Format total_amount in the response for consistency
        formatted_top_vendors = [
            {"vendor_name": v["vendor_name"], "total_amount": f"{v['total_amount']:.2f}"} 
            for v in top_vendors
        ]
        return {"status": "success", "document_type": normalized_doc_type, "top_vendors_by_amount": formatted_top_vendors}
    except Exception as e:
        print(f"ERROR in _get_top_vendors_by_total_amount_tool: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": f"Error fetching top vendors by total amount: {str(e)}"}

@mcp.tool()
def _list_all_distinct_vendors_tool(document_type: str="invoice") -> Dict[str, Any]:
    """
    TOOL: Lists all unique vendor names found for a given document type (invoices or purchase_orders).
    document_type must be 'invoice' or 'purchase_order'.
    """
    normalized_doc_type = str(document_type).strip().lower().replace(" ", "_")
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return {"status": "error", "message": "Invalid document_type. Must be 'invoice' or 'purchase_order'."}
    try:
        vendor_names = get_distinct_vendors(normalized_doc_type)
        return {"status": "success", "document_type": normalized_doc_type, "distinct_vendor_count": len(vendor_names), "vendor_names": vendor_names}
    except Exception as e:
        print(f"ERROR in _list_all_distinct_vendors_tool: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": f"Error fetching distinct vendor names: {str(e)}"}





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

def _internal_reconciliation_logic( invoice_extraction_data: dict, po_extraction_data: dict) -> dict:
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
        if _compare_strings_fuzzy_local(inv_vendor, po_vendor):
            matched_fields.append("vendor_name")
        else:
            discrepancies.append(f"Vendor Mismatch: Invoice='{inv_vendor or 'N/A'}' vs PO='{po_vendor or 'N/A'}'")

        inv_amount = invoice_data.get("total_amount")
        po_amount = po_data.get("total_amount")
        if _compare_amounts_local(inv_amount, po_amount):
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
@mcp.tool()
def _fetch_and_reconcile_documents_tool(po_number: str) -> dict:
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

        return _internal_reconciliation_logic(invoice_doc_full, po_doc_full)
    except ImportError as ie: # Catch if database_manager functions were not loaded
        print(f"ERROR in _fetch_and_reconcile_documents_tool (ImportError): {ie}\n{traceback.format_exc()}")
        return {"status": "error", "error_message": f"Database access error: {str(ie)}"}
    except Exception as e:
        # This print is for critical, unexpected errors within the tool's logic.
        print(f"ERROR in _fetch_and_reconcile_documents_tool (General Exception): {e}\n{traceback.format_exc()}")
        return {"status": "error", "error_message": f"Error fetching or preparing data for reconciliation: {str(e)}"}


if __name__=="__main__":
    mcp.run(transport="sse")