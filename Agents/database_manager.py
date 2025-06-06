import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import re

from sqlalchemy import create_engine, Column, String, Float, Index, Text, TIMESTAMP, func, inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

DB_FILE_NAME = "reconciliation_database.db"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, DB_FILE_NAME)
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Invoice(Base):
    __tablename__ = "invoices"
    invoice_number = Column(String, primary_key=True, index=True)
    vendor_name = Column(String, index=True)
    client_name = Column(String, index=True)
    invoice_date = Column(String, index=True)
    total_amount = Column(Float)
    related_po_number = Column(String, index=True)
    full_extracted_data_json = Column(Text)
    stored_at = Column(TIMESTAMP, default=datetime.utcnow)

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    po_number = Column(String, primary_key=True, index=True)
    vendor_name = Column(String, index=True)
    client_name = Column(String, index=True)
    po_date = Column(String, index=True)
    total_amount = Column(Float)
    full_extracted_data_json = Column(Text)
    stored_at = Column(TIMESTAMP, default=datetime.utcnow)

def initialize_database():
    Base.metadata.create_all(bind=engine)

def parse_and_format_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str or not isinstance(date_str, str):
        return None
    cleaned_date_str = date_str.lower()
    cleaned_date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned_date_str)
    cleaned_date_str = cleaned_date_str.replace(',', '')
    date_formats_to_try = [
        "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d",
        "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%b %d %Y", "%B %d %Y",
    ]
    for fmt in date_formats_to_try:
        try:
            dt_obj = datetime.strptime(cleaned_date_str.strip(), fmt)
            return dt_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue
    print(f"DB_MGR_SQLALCHEMY: Warning - Could not parse date string '{date_str}' (cleaned: '{cleaned_date_str}') into YYYY-MM-DD. Storing as None.")
    return None

def parse_and_format_date_old(date_str: Optional[str]) -> Optional[str]:
    if not date_str or not isinstance(date_str, str):
        return None
    cleaned_date_str = date_str.lower()
    cleaned_date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned_date_str)
    cleaned_date_str = cleaned_date_str.replace(',', '')
    cleaned_date_str = cleaned_date_str.replace('-', ' ')
    date_formats_to_try = [
    "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d",
    "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%b %d %Y", "%B %d %Y",
    ]
    for fmt in date_formats_to_try:
        try:
            dt_obj = datetime.strptime(cleaned_date_str.strip(), fmt)
            return dt_obj.strftime("%Y-%m-%d")
        except ValueError:
           continue
    print(f"DB_MGR: Warning - Could not parse date string '{date_str}' (cleaned: '{cleaned_date_str}') into YYYY-MM-DD. Storing as None.")
    return None

initialize_database()

def store_invoice_data(invoice_number: str, extracted_invoice_data: Dict[str, Any]) -> bool:
    if not invoice_number or not str(invoice_number).strip():
        print("DB_MGR_SQLALCHEMY: Error - Invoice number is empty or None.")
        return False
    invoice_number_upper = str(invoice_number).strip().upper()
    data_from_parser = extracted_invoice_data.get("data", {})
    if not data_from_parser:
        print(f"DB_MGR_SQLALCHEMY: Error - 'data' field missing for Invoice '{invoice_number_upper}'.")
        return False

    formatted_invoice_date = parse_and_format_date(data_from_parser.get("date"))
    db = SessionLocal()
    try:
        db_invoice = db.query(Invoice).filter(Invoice.invoice_number == invoice_number_upper).first()
        if db_invoice:
            db_invoice.vendor_name = data_from_parser.get("vendor_name")
            db_invoice.client_name = data_from_parser.get("client_name")
            db_invoice.invoice_date = formatted_invoice_date
            db_invoice.total_amount = data_from_parser.get("total_amount")
            db_invoice.related_po_number = str(data_from_parser.get("related_po_number","")).strip().upper() if data_from_parser.get("related_po_number") else None
            db_invoice.full_extracted_data_json = json.dumps(extracted_invoice_data)
            db_invoice.stored_at = datetime.utcnow()
        else:
            db_invoice = Invoice(
                invoice_number=invoice_number_upper,
                vendor_name=data_from_parser.get("vendor_name"),
                client_name=data_from_parser.get("client_name"),
                invoice_date=formatted_invoice_date,
                total_amount=data_from_parser.get("total_amount"),
                related_po_number=str(data_from_parser.get("related_po_number","")).strip().upper() if data_from_parser.get("related_po_number") else None,
                full_extracted_data_json=json.dumps(extracted_invoice_data),
            )
            db.add(db_invoice)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error storing invoice '{invoice_number_upper}': {e}")
        return False
    finally:
        db.close()

def store_po_data(po_number: str, extracted_po_data: Dict[str, Any]) -> bool:
    if not po_number or not str(po_number).strip():
        print("DB_MGR_SQLALCHEMY: Error - PO number is empty or None.")
        return False
    po_number_upper = str(po_number).strip().upper()
    data_from_parser = extracted_po_data.get("data", {})
    if not data_from_parser:
        print(f"DB_MGR_SQLALCHEMY: Error - 'data' field missing for PO '{po_number_upper}'.")
        return False

    formatted_po_date = parse_and_format_date(data_from_parser.get("date"))
    db = SessionLocal()
    try:
        db_po = db.query(PurchaseOrder).filter(PurchaseOrder.po_number == po_number_upper).first()
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
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error storing PO '{po_number_upper}': {e}")
        return False
    finally:
        db.close()

def get_invoice_by_number(invoice_number: str) -> Optional[Dict[str, Any]]:
    if not invoice_number or not str(invoice_number).strip(): return None
    inv_num_upper = str(invoice_number).strip().upper()
    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter(Invoice.invoice_number == inv_num_upper).first()
        if invoice and invoice.full_extracted_data_json:
            return json.loads(invoice.full_extracted_data_json)
        else: print(f"DB_MGR_SQLALCHEMY: Invoice '{inv_num_upper}' not found.")
        return None
    except SQLAlchemyError as e:
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching invoice '{inv_num_upper}': {e}")
    except json.JSONDecodeError as je:
        print(f"DB_MGR_SQLALCHEMY: Error decoding JSON for invoice '{inv_num_upper}': {je}")
    finally:
        db.close()
    return None

def get_po_by_number(po_number: str) -> Optional[Dict[str, Any]]:
    if not po_number or not str(po_number).strip(): return None
    po_num_upper = str(po_number).strip().upper()
    db = SessionLocal()
    try:
        po = db.query(PurchaseOrder).filter(PurchaseOrder.po_number == po_num_upper).first()
        if po and po.full_extracted_data_json:
            return json.loads(po.full_extracted_data_json)
        else: print(f"DB_MGR_SQLALCHEMY: PO '{po_num_upper}' not found.")
        return None
    except SQLAlchemyError as e:
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching PO '{po_num_upper}': {e}")
    except json.JSONDecodeError as je:
        print(f"DB_MGR_SQLALCHEMY: Error decoding JSON for PO '{po_num_upper}': {je}")
    finally:
        db.close()
    return None

def get_invoice_by_related_po(po_number: str) -> Optional[Dict[str, Any]]:
    if not po_number or not str(po_number).strip(): return None
    related_po_num_upper = str(po_number).strip().upper()
    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter(Invoice.related_po_number == related_po_num_upper).first()
        if invoice and invoice.full_extracted_data_json:
            return json.loads(invoice.full_extracted_data_json)
        else: print(f"DB_MGR_SQLALCHEMY: No Invoice found in DB that references PO '{related_po_num_upper}'.")
        return None
    except SQLAlchemyError as e:
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching invoice by related PO '{related_po_num_upper}': {e}")
    except json.JSONDecodeError as je:
        print(f"DB_MGR_SQLALCHEMY: Error decoding JSON for invoice related to PO '{related_po_num_upper}': {je}")
    finally:
        db.close()
    return None

def get_all_invoices() -> List[Dict[str, Any]]:
    db = SessionLocal()
    results = []
    try:
        invoices = db.query(Invoice.full_extracted_data_json).all()
        for inv_json_tuple in invoices:
            if inv_json_tuple[0]:
                try:
                    results.append(json.loads(inv_json_tuple[0]))
                except json.JSONDecodeError as je:
                    print(f"DB_MGR_SQLALCHEMY: Error decoding JSON for an invoice in get_all_invoices: {je}")
        return results
    except SQLAlchemyError as e:
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching all invoices: {e}")
        return []
    finally:
        db.close()

def get_all_purchase_orders() -> List[Dict[str, Any]]:
    db = SessionLocal()
    results = []
    try:
        pos = db.query(PurchaseOrder.full_extracted_data_json).all()
        for po_json_tuple in pos:
            if po_json_tuple[0]:
                try:
                    results.append(json.loads(po_json_tuple[0]))
                except json.JSONDecodeError as je:
                    print(f"DB_MGR_SQLALCHEMY: Error decoding JSON for a PO in get_all_purchase_orders: {je}")
        return results
    except SQLAlchemyError as e:
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching all POs: {e}")
        return []
    finally:
        db.close()

def clear_database():
    db = SessionLocal()
    try:
        db.query(Invoice).delete()
        db.query(PurchaseOrder).delete()
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error clearing database: {e}")
    finally:
        db.close()

def get_documents_count_by_date_range(doc_type: str, start_date_str: str, end_date_str: str) -> int:
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return 0
    
    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder
    date_column_attr = Invoice.invoice_date if normalized_doc_type == "invoice" else PurchaseOrder.po_date

    try:
        datetime.strptime(start_date_str, "%Y-%m-%d")
        datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        print(f"DB_MGR_SQLALCHEMY: Invalid date format for '{start_date_str}' or '{end_date_str}'. Expected YYYY-MM-DD.")
        return 0
    
    db = SessionLocal()
    count = 0
    try:
        count = db.query(func.count(Model.invoice_number if normalized_doc_type == "invoice" else Model.po_number))\
                  .filter(date_column_attr >= start_date_str, date_column_attr <= end_date_str)\
                  .scalar()
        count = count if count is not None else 0
    except SQLAlchemyError as e:
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error counting {normalized_doc_type} by date range: {e}")
    finally:
        db.close()
    return count

def get_documents_count_by_vendor(doc_type: str, vendor_name: str) -> int:
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return 0
    
    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder
    
    db = SessionLocal()
    count = 0
    try:
        count = db.query(func.count(Model.invoice_number if normalized_doc_type == "invoice" else Model.po_number))\
                  .filter(Model.vendor_name.like(f"%{vendor_name}%"))\
                  .scalar()
        count = count if count is not None else 0
    except SQLAlchemyError as e:
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error counting {normalized_doc_type} by vendor: {e}")
    finally:
        db.close()
    return count

def get_total_amount_by_vendor(doc_type: str, vendor_name: str) -> float:
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return 0.0
    
    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder
    
    db = SessionLocal()
    total_amount = 0.0
    try:
        sum_result = db.query(func.sum(Model.total_amount))\
                       .filter(Model.vendor_name.like(f"%{vendor_name}%"))\
                       .scalar()
        if sum_result is not None:
            total_amount = float(sum_result)
    except SQLAlchemyError as e:
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error summing {normalized_doc_type} amounts by vendor: {e}")
    except (TypeError, ValueError):
        print(f"DB_MGR_SQLALCHEMY: No numeric amounts found or conversion error for {normalized_doc_type} from vendor like '{vendor_name}'.")
    finally:
        db.close()
    return total_amount

def _extract_data_field_from_json_str(json_str: Optional[str]) -> Optional[Dict[str, Any]]:
    if json_str:
        try:
            full_data = json.loads(json_str)
            return full_data.get("data", {})
        except json.JSONDecodeError as je:
            print(f"DB_MGR_SQLALCHEMY: Warning - Could not decode JSON to extract 'data' field: {je}")
            return {}
    return {}

def get_documents_by_vendor(doc_type: str, vendor_name: str, limit: int = 5) -> List[Dict[str, Any]]:
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return []
    
    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder
    
    results = []
    db = SessionLocal()
    try:
        documents_json = db.query(Model.full_extracted_data_json)\
                           .filter(Model.vendor_name.like(f"%{vendor_name}%"))\
                           .limit(limit)\
                           .all()
        for doc_json_tuple in documents_json:
            data_field = _extract_data_field_from_json_str(doc_json_tuple[0])
            if data_field:
                results.append(data_field)
    except SQLAlchemyError as e:
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching {normalized_doc_type} by vendor: {e}")
    finally:
        db.close()
    return results

def get_documents_by_date_range(doc_type: str, start_date_str: str, end_date_str: str, limit: int = 5) -> List[Dict[str, Any]]:
    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type not in ["invoice", "purchase_order"]:
        return []

    Model = Invoice if normalized_doc_type == "invoice" else PurchaseOrder
    date_column_attr = Invoice.invoice_date if normalized_doc_type == "invoice" else PurchaseOrder.po_date

    try:
        datetime.strptime(start_date_str, "%Y-%m-%d")
        datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        print(f"DB_MGR_SQLALCHEMY: Invalid date format for '{start_date_str}' or '{end_date_str}'. Expected YYYY-MM-DD.")
        return []

    results = []
    db = SessionLocal()
    try:
        documents_json = db.query(Model.full_extracted_data_json)\
                           .filter(date_column_attr >= start_date_str, date_column_attr <= end_date_str)\
                           .limit(limit)\
                           .all()
        for doc_json_tuple in documents_json:
            data_field = _extract_data_field_from_json_str(doc_json_tuple[0])
            if data_field:
                results.append(data_field)
    except SQLAlchemyError as e:
        print(f"DB_MGR_SQLALCHEMY: SQLAlchemy error fetching {normalized_doc_type} by date range: {e}")
    finally:
        db.close()
    return results
