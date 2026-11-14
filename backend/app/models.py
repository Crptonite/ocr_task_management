"""SQLAlchemy models for everything the workspace keeps.

Owner: Aeric (backend). One table per collection in app.store. Header fields are typed columns so
the data can be queried in SQLite or the Supabase SQL editor; line items and nested workflow data
(approval, invoice draft, status history) are JSON. `extra` holds any other key a record carries
(extraction notes, confidence, audit fields), so a record survives the round trip unchanged.

Dates stay ISO strings (YYYY-MM-DD): that is what the API and the frontend use, and extracted
documents can carry dates that are not valid calendar dates until staff correct them.
"""
from typing import Any

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON, float: Float, str: String}


class Record(Base):
    """Shared columns: `pk` is internal, `position` keeps the list order the app shows."""
    __abstract__ = True

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position: Mapped[int] = mapped_column(Integer, index=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


# ---- Koda: supplier invoices vs purchase orders ----

class PurchaseOrder(Record):
    __tablename__ = "purchase_orders"

    po_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    supplier: Mapped[str | None]
    currency: Mapped[str | None]
    auto_created: Mapped[bool | None] = mapped_column(Boolean)
    source_invoice: Mapped[str | None]
    lines: Mapped[list[Any]] = mapped_column(JSON, default=list)


class SupplierInvoice(Record):
    # invoice_number is not unique on purpose: a re-sent invoice is kept and flagged as a duplicate.
    __tablename__ = "supplier_invoices"

    invoice_number: Mapped[str] = mapped_column(String, index=True)
    po_number: Mapped[str | None] = mapped_column(String, index=True)
    supplier: Mapped[str | None]
    invoice_date: Mapped[str | None]
    currency: Mapped[str | None]
    tax_rate: Mapped[float | None]
    tax_amount: Mapped[float | None]
    lines: Mapped[list[Any]] = mapped_column(JSON, default=list)
    source_file: Mapped[str | None]
    file_path: Mapped[str | None]  # Supabase Storage path of the uploaded document
    auto_filled: Mapped[list[Any] | None] = mapped_column(JSON)


# ---- Spectra: orders ----

class CatalogItem(Record):
    __tablename__ = "catalog_items"

    sku: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str]
    unit_price: Mapped[float]


class Order(Record):
    """approval, invoice (the Review Invoice Queue draft) and status_history live in `extra`."""
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, unique=True, index=True)
    order_number: Mapped[str | None] = mapped_column(String, index=True)
    transaction_id: Mapped[str | None]
    type: Mapped[str | None]
    counterparty: Mapped[str | None]
    order_date: Mapped[str | None]
    delivery_date: Mapped[str | None]
    currency: Mapped[str | None]
    total: Mapped[float | None]
    status: Mapped[str] = mapped_column(String, index=True)
    source_file: Mapped[str | None]
    lines: Mapped[list[Any]] = mapped_column(JSON, default=list)


# ---- EM Services: projects ----

class Member(Record):
    __tablename__ = "members"

    name: Mapped[str] = mapped_column(String, unique=True)


class Project(Record):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str]
    site: Mapped[str | None]
    owner: Mapped[str | None]
    brief: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[str | None]
    due_date: Mapped[str | None]


class Task(Record):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, unique=True, index=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str]
    owner: Mapped[str | None]
    due_date: Mapped[str | None]
    status: Mapped[str]


# ---- Koda: production planning ----

class Product(Record):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str]
    bom: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # material sku -> qty per unit


class Material(Record):
    __tablename__ = "materials"

    sku: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str]
    on_hand: Mapped[float]
    unit: Mapped[str | None]


class InboundDelivery(Record):
    __tablename__ = "inbound_deliveries"

    po_number: Mapped[str | None]
    sku: Mapped[str] = mapped_column(String, index=True)
    qty: Mapped[float]
    eta: Mapped[str | None]


class Demand(Record):
    __tablename__ = "demand"

    order_number: Mapped[str] = mapped_column(String, index=True)
    customer: Mapped[str | None]
    product: Mapped[str]
    quantity: Mapped[float]
    due_date: Mapped[str | None]
