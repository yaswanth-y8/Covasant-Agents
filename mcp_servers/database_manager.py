"""
Database manager for handling storage and retrieval of invoice and purchase order
data using SQLAlchemy with a SQLite backend.
Provides functions for CRUD operations and some analytical queries.
"""
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import re

from sqlalchemy import create_engine, Column, String, Float, Text, TIMESTAMP, func, desc, distinct
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

# Using a static string for DATABASE_URL as os.path.join was not used
# and f-string was not interpolating.
# Ensure this path is correct for your environment.
DATABASE_URL = "sqlite:///C:/Users/Sai Charan/Desktop/ADK/vendor_reconcilliation/reconciliation_database.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Invoice(Base): # pylint: disable=too-few-public-methods
    """SQLAlchemy model for invoices."""
    __tablename__ = "invoices"
    invoice_number = Column(String, primary_key=True, index=True)
    vendor_name = Column(String, index=True)
    client_name = Column(String, index=True)
    invoice_date = Column(String, index=True)
    total_amount = Column(Float)
    related_po_number = Column(String, index=True)
    full_extracted_data_json = Column(Text)
    stored_at = Column(TIMESTAMP, default=datetime.utcnow)

class PurchaseOrder(Base): # pylint: disable=too-few-public-methods
    """SQLAlchemy model for purchase orders."""
    __tablename__ = "purchase_orders"
    po_number = Column(String, primary_key=True, index=True)
    vendor_name = Column(String, index=True)
    client_name = Column(String, index=True)
    po_date = Column(String, index=True)
    total_amount = Column(Float)
    full_extracted_data_json = Column(Text)
    stored_at = Column(TIMESTAMP, default=datetime.utcnow)

def initialize_database():
    """Creates all database tables defined in Base.metadata if they don't exist."""
    Base.metadata.create_all(bind=engine)

def parse_and_format_date(date_str: Optional[str]) -> Optional[str]:
    """
    Parses a date string from various common formats and returns it in YYYY-MM-DD format.
    Returns None if parsing fails.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    cleaned_date_str = date_str.lower()
    cleaned_date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned_date_str)
    cleaned_date_str = cleaned_date_str.replace(',', '')
    date_formats_to_try = [
        "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d",
        "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", # Fixed: missing comma in original list
    ]
    for fmt in date_formats_to_try:
        try:
            dt_obj = datetime.strptime(cleaned_date_str.strip(), fmt)
            return dt_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # print(
    #    f"DB_MGR_SQLALCHEMY: Warning - Could not parse date string '{date_str}' "
    #    f"(cleaned: '{cleaned_date_str}') into YYYY-MM-DD. Storing as None."
    # )
    return None

def parse_and_format_date_old(date_str: Optional[str]) -> Optional[str]:
    """
    Attempts to parse a date string from various formats into YYYY-MM-DD.
    This is an older version, consider using `parse_and_format_date`.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    cleaned_date_str = date_str.lower()
    cleaned_date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned_date_str)
    cleaned_date_str = cleaned_date_str.replace(',', '')
    cleaned_date_str = cleaned_date_str.replace('-', ' ') # Different from new function
    date_formats_to_try = [
        "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d",
        "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d",
    ]
    for fmt in date_formats_to_try:
        try:
            dt_obj = datetime.strptime(cleaned_date_str.strip(), fmt)
            return dt_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # print(
    #    f"DB_MGR: Warning - Could not parse date string '{date_str}' "
    #    f"(cleaned: '{cleaned_date_str}') into YYYY-MM-DD. Storing as None."
    # )
    return None

initialize_database()

def store_invoice_data(
    invoice_number: str, extracted_invoice_data: Dict[str, Any]
) -> bool:
    """
    Stores or updates an invoice in the database.
    """
    if not invoice_number or not str(invoice_number).strip():
        # print("DB_MGR_SQLALCHEMY: Error - Invoice number is empty or None.")
        return False
    invoice_number_upper = str(invoice_number).strip().upper()
    data_from_parser = extracted_invoice_data.get("data", {})
    if not data_from_parser:
        # print(
        #    f"DB_MGR_SQLALCHEMY: Error - 'data' field missing for Invoice "
        #    f"'{invoice_number_upper}'."
        # )
        return False

    formatted_invoice_date = parse_and_format_date(data_from_parser.get("date"))
    related_po_num = data_from_parser.get("related_po_number")
    related_po_num_upper = (
        str(related_po_num).strip().upper() if related_po_num else None
    )

    db = SessionLocal()
    try:
        db_invoice = (
            db.query(Invoice)
            .filter(Invoice.invoice_number == invoice_number_upper)
            .first()
        )
        if db_invoice:
            db_invoice.vendor_name = data_from_parser.get("vendor_name")
            db_invoice.client_name = data_from_parser.get("client_name")
            db_invoice.invoice_date = formatted_invoice_date
            db_invoice.total_amount = data_from_parser.get("total_amount")
            db_invoice.related_po_number = related_po_num_upper
            db_invoice.full_extracted_data_json = json.dumps(extracted_invoice_data)
            db_invoice.stored_at = datetime.utcnow()
        else:
            db_invoice = Invoice(
                invoice_number=invoice_number_upper,
                vendor_name=data_from_parser.get("vendor_name"),
                client_name=data_from_parser.get("client_name"),
                invoice_date=formatted_invoice_date,
                total_amount=data_from_parser.get("total_amount"),
                related_po_number=related_po_num_upper,
                full_extracted_data_json=json.dumps(extracted_invoice_data),
            )
            db.add(db_invoice)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        # print(
        #    f"DB_MGR_SQLALCHEMY: SQLAlchemy error storing invoice "
        #    f"'{invoice_number_upper}': {e}"
        # )
        return False
    finally:
        db.close()

def store_po_data(po_number: str, extracted_po_data: Dict[str, Any]) -> bool:
    """
    Stores or updates a purchase order in the database.
    """
    if not po_number or not str(po_number).strip():
        # print("DB_MGR_SQLALCHEMY: Error - PO number is empty or None.")
        return False
    po_number_upper = str(po_number).strip().upper()
    data_from_parser = extracted_po_data.get("data", {})
    if not data_from_parser:
        # print(
        #    f"DB_MGR_SQLALCHEMY: Error - 'data' field missing for PO '{po_number_upper}'."
        # )
        return False

    formatted_po_date = parse_and_format_date(data_from_parser.get("date"))
    db = SessionLocal()
    try:
        db_po = (
            db.query(PurchaseOrder)
            .filter(PurchaseOrder.po_number == po_number_upper)
            .first()
        )
        if db_po:
            db_po.vendor_name = data_from_parser.get("vendor_name")
            db_po.client_name = data_from_parser.get("client_name")
            db_po.po_date = formatted_po_date
            db_po.total_amount = data_from_parser.get("total_amount")
            db_po.full_extracted_data_json = json.dumps(extracted_po_data)
            db_po.stored_at = datetime.utcnow()
        else:
            db_po = PurchaseOrder(
                po_number=po_number_upper,
                vendor_name=data_from_parser.get("vendor_name"),
                client_name=data_from_parser.get("client_name"),
                po_date=formatted_po_date,
                total_amount=data_from_parser.get("total_amount"),
                full_extracted_data_json=json.dumps(extracted_po_data),
            )
            db.add(db_po)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        # print(
        #    f"DB_MGR_SQLALCHEMY: SQLAlchemy error storing PO '{po_number_upper}': {e}"
        # )
        return False
    finally:
        db.close()

def get_invoice_by_number(invoice_number: str) -> Optional[Dict[str, Any]]:
    """Retrieves full stored JSON for an invoice by its number."""
    if not invoice_number or not str(invoice_number).strip():
        return None
    inv_num_upper = str(invoice_number).strip().upper()
    db = SessionLocal()
    try:
        invoice = (
            db.query(Invoice)
            .filter(Invoice.invoice_number == inv_num_upper)
            .first()
        )
        if invoice and invoice.full_extracted_data_json:
            return json.loads(invoice.full_extracted_data_json)
        # print(f"DB_MGR_SQLALCHEMY: Invoice '{inv_num_upper}' not found.")
        return None
    except SQLAlchemyError as e:
        # print(
        #    f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching invoice '{inv_num_upper}': {e}"
        # )
        return None # Added return for consistency
    except json.JSONDecodeError as je:
        # print(
        #    f"DB_MGR_SQLALCHEMY: Error decoding JSON for invoice '{inv_num_upper}': {je}"
        # )
        return None # Added return for consistency
    finally:
        db.close()
    # return None # This was redundant due to returns in except blocks

def get_po_by_number(po_number: str) -> Optional[Dict[str, Any]]:
    """Retrieves full stored JSON for a purchase order by its number."""
    if not po_number or not str(po_number).strip():
        return None
    po_num_upper = str(po_number).strip().upper()
    db = SessionLocal()
    try:
        po_order = ( # Renamed variable to avoid conflict with 'po' from 'import os' if it were used
            db.query(PurchaseOrder)
            .filter(PurchaseOrder.po_number == po_num_upper)
            .first()
        )
        if po_order and po_order.full_extracted_data_json:
            return json.loads(po_order.full_extracted_data_json)
        # print(f"DB_MGR_SQLALCHEMY: PO '{po_num_upper}' not found.")
        return None
    except SQLAlchemyError as e:
        # print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching PO '{po_num_upper}': {e}")
        return None # Added return
    except json.JSONDecodeError as je:
        # print(f"DB_MGR_SQLALCHEMY: Error decoding JSON for PO '{po_num_upper}': {je}")
        return None # Added return
    finally:
        db.close()
    # return None # Redundant

def get_invoice_by_related_po(po_number: str) -> Optional[Dict[str, Any]]:
    """Retrieves full stored JSON for an invoice by a PO number it references."""
    if not po_number or not str(po_number).strip():
        return None
    related_po_num_upper = str(po_number).strip().upper()
    db = SessionLocal()
    try:
        invoice = (
            db.query(Invoice)
            .filter(Invoice.related_po_number == related_po_num_upper)
            .first()
        )
        if invoice and invoice.full_extracted_data_json:
            return json.loads(invoice.full_extracted_data_json)
        # print(
        #    f"DB_MGR_SQLALCHEMY: No Invoice found in DB that references PO "
        #    f"'{related_po_num_upper}'."
        # )
        return None
    except SQLAlchemyError as e:
        # print(
        #    f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching invoice by related PO "
        #    f"'{related_po_num_upper}': {e}"
        # )
        return None
    except json.JSONDecodeError as je:
        # print(
        #    f"DB_MGR_SQLALCHEMY: Error decoding JSON for invoice related to PO "
        #    f"'{related_po_num_upper}': {je}"
        # )
        return None
    finally:
        db.close()
    # return None # Redundant

def get_all_invoices() -> List[Dict[str, Any]]:
    """Returns a list of all stored invoices (full JSON objects)."""
    db = SessionLocal()
    results = []
    try:
        invoices_json_tuples = db.query(Invoice.full_extracted_data_json).all()
        for inv_json_tuple in invoices_json_tuples:
            if inv_json_tuple[0]:
                try:
                    results.append(json.loads(inv_json_tuple[0]))
                except json.JSONDecodeError as je:
                    pass
                    # print(
                    #    f"DB_MGR_SQLALCHEMY: Error decoding JSON for an invoice in "
                    #    f"get_all_invoices: {je}"
                    # )
        return results
    except SQLAlchemyError as e:
        # print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching all invoices: {e}")
        return []
    finally:
        db.close()

def get_all_purchase_orders() -> List[Dict[str, Any]]:
    """Returns a list of all stored purchase orders (full JSON objects)."""
    db = SessionLocal()
    results = []
    try:
        pos_json_tuples = db.query(PurchaseOrder.full_extracted_data_json).all()
        for po_json_tuple in pos_json_tuples:
            if po_json_tuple[0]:
                try:
                    results.append(json.loads(po_json_tuple[0]))
                except json.JSONDecodeError as je:
                    pass
                    # print(
                    #    f"DB_MGR_SQLALCHEMY: Error decoding JSON for a PO in "
                    #    f"get_all_purchase_orders: {je}"
                    # )
        return results
    except SQLAlchemyError as e:
        # print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching all POs: {e}")
        return []
    finally:
        db.close()

def clear_database():
    """Clears all data from invoices and purchase_orders tables."""
    db = SessionLocal()
    try:
        db.query(Invoice).delete()
        db.query(PurchaseOrder).delete()
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        # print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error clearing database: {e}")
    finally:
        db.close()

def get_documents_count_by_date_range(
    doc_type: str, start_date_str: str, end_date_str: str
) -> int:
    """Counts documents of a given type within a date range."""
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return 0

    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder
    date_column = (
        Invoice.invoice_date
        if normalized_doc_type == "invoice"
        else PurchaseOrder.po_date
    )
    pk_column = (
        Invoice.invoice_number
        if normalized_doc_type == "invoice"
        else PurchaseOrder.po_number
    )

    try:
        datetime.strptime(start_date_str, "%Y-%m-%d")
        datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        # print(
        #    f"DB_MGR_SQLALCHEMY: Invalid date format for '{start_date_str}' or "
        #    f"'{end_date_str}'. Expected YYYY-MM-DD."
        # )
        return 0

    db = SessionLocal()
    count = 0
    try:
        count_query = db.query(func.count(pk_column)) # Use specific column for count
        count = (
            count_query.filter(date_column >= start_date_str, date_column <= end_date_str)
            .scalar()
        )
        count = count if count is not None else 0
    except SQLAlchemyError as e:
        pass
        # print(
        #    f"DB_MGR_SQLALCHEMY: SQLAlchemy error counting {normalized_doc_type} "
        #    f"by date range: {e}"
        # )
    finally:
        db.close()
    return count

def get_documents_count_by_vendor(doc_type: str, vendor_name: str) -> int:
    """Counts documents of a given type for a specific vendor (case-insensitive like)."""
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return 0

    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder
    pk_column = (
        Invoice.invoice_number
        if normalized_doc_type == "invoice"
        else PurchaseOrder.po_number
    )

    db = SessionLocal()
    count = 0
    try:
        count_query = db.query(func.count(pk_column)) # Use specific column for count
        count = (
            count_query.filter(Model.vendor_name.ilike(f"%{vendor_name}%")) # ilike for case-insensitive
            .scalar()
        )
        count = count if count is not None else 0
    except SQLAlchemyError as e:
        pass
        # print(
        #    f"DB_MGR_SQLALCHEMY: SQLAlchemy error counting {normalized_doc_type} "
        #    f"by vendor: {e}"
        # )
    finally:
        db.close()
    return count

def get_total_amount_by_vendor(doc_type: str, vendor_name: str) -> float:
    """Calculates total amount for documents of a type from a specific vendor."""
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return 0.0

    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder

    db = SessionLocal()
    total_amount = 0.0
    try:
        sum_query = db.query(func.sum(Model.total_amount))
        sum_result = (
            sum_query.filter(Model.vendor_name.ilike(f"%{vendor_name}%")) # ilike
            .scalar()
        )
        if sum_result is not None:
            total_amount = float(sum_result)
    except SQLAlchemyError as e:
        pass
        # print(
        #    f"DB_MGR_SQLALCHEMY: SQLAlchemy error summing {normalized_doc_type} "
        #    f"amounts by vendor: {e}"
        # )
    except (TypeError, ValueError):
        pass
        # print(
        #    f"DB_MGR_SQLALCHEMY: No numeric amounts found or conversion error for "
        #    f"{normalized_doc_type} from vendor like '{vendor_name}'."
        # )
    finally:
        db.close()
    return total_amount

def _extract_data_field_from_json_str(
    json_str: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Safely extracts the 'data' field from a JSON string."""
    if json_str:
        try:
            full_data = json.loads(json_str)
            return full_data.get("data", {}) # Return empty dict if 'data' not found
        except json.JSONDecodeError as je:
            # print(
            #    f"DB_MGR_SQLALCHEMY: Warning - Could not decode JSON to extract "
            #    f"'data' field: {je}"
            # )
            return {} # Return empty dict on error
    return {} # Return empty dict if json_str is None

def get_documents_by_vendor(
    doc_type: str, vendor_name: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """Retrieves the 'data' field of documents for a vendor, up to a limit."""
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return []

    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder

    results = []
    db = SessionLocal()
    try:
        documents_json_tuples = (
            db.query(Model.full_extracted_data_json)
            .filter(Model.vendor_name.ilike(f"%{vendor_name}%")) # ilike
            .limit(limit)
            .all()
        )
        for doc_json_tuple in documents_json_tuples:
            data_field = _extract_data_field_from_json_str(doc_json_tuple[0])
            if data_field: # Ensure data_field is not empty or None
                results.append(data_field)
    except SQLAlchemyError as e:
        pass
        # print(
        #    f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching {normalized_doc_type} "
        #    f"by vendor: {e}"
        # )
    finally:
        db.close()
    return results

def get_documents_by_date_range(
    doc_type: str, start_date_str: str, end_date_str: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """Retrieves 'data' field of documents in a date range, up to a limit."""
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return []

    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder
    date_column = (
        Invoice.invoice_date
        if normalized_doc_type == "invoice"
        else PurchaseOrder.po_date
    )

    try:
        datetime.strptime(start_date_str, "%Y-%m-%d")
        datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        # print(
        #    f"DB_MGR_SQLALCHEMY: Invalid date format for '{start_date_str}' or "
        #    f"'{end_date_str}'. Expected YYYY-MM-DD."
        # )
        return []

    results = []
    db = SessionLocal()
    try:
        documents_json_tuples = (
            db.query(Model.full_extracted_data_json)
            .filter(date_column >= start_date_str, date_column <= end_date_str)
            .limit(limit)
            .all()
        )
        for doc_json_tuple in documents_json_tuples:
            data_field = _extract_data_field_from_json_str(doc_json_tuple[0])
            if data_field: # Ensure data_field is not empty or None
                results.append(data_field)
    except SQLAlchemyError as e:
        pass
        # print(
        #    f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching {normalized_doc_type} "
        #    f"by date range: {e}"
        # )
    finally:
        db.close()
    return results

# Added previously from another request:
def get_top_vendors_by_document_count(
    doc_type: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """Retrieves top vendors by document count."""
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return []

    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder
    pk_column = (
        Invoice.invoice_number
        if normalized_doc_type == "invoice"
        else PurchaseOrder.po_number
    )

    results = []
    db = SessionLocal()
    try:
        top_vendors_query = (
            db.query(Model.vendor_name, func.count(pk_column).label("document_count"))
            .group_by(Model.vendor_name)
            .order_by(desc("document_count"))
            .limit(limit)
            .all()
        )
        for vendor_name, count in top_vendors_query:
            results.append({"vendor_name": vendor_name, "document_count": count})
    except SQLAlchemyError as e:
        # print(
        #    f"DB_MGR_SQLALCHEMY: Error fetching top vendors by count for "
        #    f"{normalized_doc_type}: {e}"
        # )
        pass
    finally:
        db.close()
    return results

def get_top_vendors_by_total_amount(
    doc_type: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """Retrieves top vendors by total document amount."""
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return []

    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder

    results = []
    db = SessionLocal()
    try:
        top_vendors_query = (
            db.query(
                Model.vendor_name, func.sum(Model.total_amount).label("total_amount_sum")
            )
            .group_by(Model.vendor_name)
            .order_by(desc("total_amount_sum"))
            .limit(limit)
            .all()
        )
        for vendor_name, total_sum in top_vendors_query:
            results.append({
                "vendor_name": vendor_name,
                "total_amount": float(total_sum) if total_sum else 0.0
            })
    except SQLAlchemyError as e:
        # print(
        #    f"DB_MGR_SQLALCHEMY: Error fetching top vendors by amount for "
        #    f"{normalized_doc_type}: {e}"
        # )
        pass
    finally:
        db.close()
    return results

def get_distinct_vendors(doc_type: str) -> List[str]:
    """Retrieves a list of unique vendor names for a document type."""
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return []

    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder

    vendor_names = []
    db = SessionLocal()
    try:
        distinct_vendors_query = (
            db.query(distinct(Model.vendor_name))
            .filter(Model.vendor_name.isnot(None))
            .order_by(Model.vendor_name)
            .all()
        )
        vendor_names = [
            name_tuple[0] for name_tuple in distinct_vendors_query if name_tuple[0]
        ]
    except SQLAlchemyError as e:
        # print(
        #    f"DB_MGR_SQLALCHEMY: Error fetching distinct vendors for "
        #    f"{normalized_doc_type}: {e}"
        # )
        pass
    finally:
        db.close()
    return vendor_names

def get_overall_document_summary_by_date_range(
    doc_type: str,
    start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates overall count and total amount for a document type,
    optionally filtered by a date range.
    """
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return {"total_count": 0, "total_amount": 0.0, "error": "Invalid document type"}

    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder
    date_column = (
        Invoice.invoice_date
        if normalized_doc_type == "invoice"
        else PurchaseOrder.po_date
    )
    pk_column = (
        Invoice.invoice_number
        if normalized_doc_type == "invoice"
        else PurchaseOrder.po_number
    )

    summary = {"total_count": 0, "total_amount": 0.0}
    db = SessionLocal()
    try:
        query = db.query(
            func.count(pk_column).label("count"), # Use specific PK column
            func.sum(Model.total_amount).label("amount_sum")
        )

        if start_date_str:
            try:
                datetime.strptime(start_date_str, "%Y-%m-%d")
                query = query.filter(date_column >= start_date_str)
            except ValueError:
                # print(
                #    f"DB_MGR_SQLALCHEMY: Invalid start_date format '{start_date_str}'. "
                #    f"Ignoring for summary."
                # )
                pass # Or set summary["error_start_date"] = "Invalid format"

        if end_date_str:
            try:
                datetime.strptime(end_date_str, "%Y-%m-%d")
                query = query.filter(date_column <= end_date_str)
            except ValueError:
                # print(
                #    f"DB_MGR_SQLALCHEMY: Invalid end_date format '{end_date_str}'. "
                #    f"Ignoring for summary."
                # )
                pass # Or set summary["error_end_date"] = "Invalid format"

        result = query.one_or_none()

        if result:
            summary["total_count"] = result.count if result.count is not None else 0
            summary["total_amount"] = (
                float(result.amount_sum) if result.amount_sum is not None else 0.0
            )
    except SQLAlchemyError as e:
        # print(
        #    f"DB_MGR_SQLALCHEMY: Error fetching overall summary for "
        #    f"{normalized_doc_type}: {e}"
        # )
        summary["error"] = str(e)
    finally:
        db.close()
    return summary