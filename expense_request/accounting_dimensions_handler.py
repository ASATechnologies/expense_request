# accounting_dimension_handler.py
# Updated to work with your existing DocType structure

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe import _


def on_dimension_change(doc, method):
    """Handle accounting dimension creation/update"""
    if method in ["after_insert", "on_update"]:
        create_dimension_fields(doc)


def on_dimension_delete(doc, method):
    """Handle accounting dimension deletion"""
    delete_dimension_fields(doc)


def create_dimension_fields(dimension_doc):
    """Create custom fields for a new accounting dimension"""

    fieldname = dimension_doc.fieldname
    label = dimension_doc.label
    document_type = dimension_doc.document_type

    # Skip if this dimension already exists as a default field in the DocType
    existing_default_fields = ["default_project", "default_cost_center"]
    existing_item_fields = ["project", "cost_center"]

    default_fieldname = f"default_{fieldname}"

    try:
        # Add default dimension field to parent Expense Entry (only if not already in DocType)
        if default_fieldname not in existing_default_fields and not frappe.db.exists(
            "Custom Field", {"dt": "Expense Entry", "fieldname": default_fieldname}
        ):

            create_custom_field(
                "Expense Entry",
                {
                    "fieldname": default_fieldname,
                    "label": f"Default {label}",
                    "fieldtype": "Link",
                    "options": document_type,
                    "insert_after": get_insert_after_field("Expense Entry"),
                    "in_list_view": 0,
                    "in_standard_filter": 1,
                    "reqd": 0,
                    "description": f"Applies to all expenses below unless specified differently",
                },
            )
            print(f"Created default field for {label}")

        # Add dimension field to child table (only if not already in DocType)
        if fieldname not in existing_item_fields and not frappe.db.exists(
            "Custom Field", {"dt": "Expense Entry Item", "fieldname": fieldname}
        ):

            create_custom_field(
                "Expense Entry Item",
                {
                    "fieldname": fieldname,
                    "label": label,
                    "fieldtype": "Link",
                    "options": document_type,
                    "insert_after": get_insert_after_field("Expense Entry Item"),
                    "in_list_view": 1,
                    "reqd": 1 if dimension_doc.mandatory_for_pl else 0,
                    "columns": 2,
                },
            )
            print(f"Created item field for {label}")

        frappe.msgprint(
            _("Accounting dimension fields created for {0}").format(label),
            alert=True,
            indicator="green",
        )

    except Exception as e:
        frappe.log_error(f"Error creating dimension fields for {label}: {str(e)}")
        frappe.throw(
            _("Error creating fields for accounting dimension {0}").format(label)
        )


def delete_dimension_fields(dimension_doc):
    """Delete custom fields for a deleted accounting dimension (only custom fields, not DocType fields)"""

    fieldname = dimension_doc.fieldname
    default_fieldname = f"default_{fieldname}"

    # Don't delete fields that are part of the core DocType
    protected_fields = [
        "default_project",
        "default_cost_center",
        "project",
        "cost_center",
    ]

    try:
        # Delete from Expense Entry (only if it's a custom field)
        if default_fieldname not in protected_fields:
            parent_field = frappe.db.exists(
                "Custom Field", {"dt": "Expense Entry", "fieldname": default_fieldname}
            )
            if parent_field:
                frappe.delete_doc("Custom Field", parent_field)

        # Delete from Expense Entry Item (only if it's a custom field)
        if fieldname not in protected_fields:
            child_field = frappe.db.exists(
                "Custom Field", {"dt": "Expense Entry Item", "fieldname": fieldname}
            )
            if child_field:
                frappe.delete_doc("Custom Field", child_field)

        frappe.msgprint(
            _("Accounting dimension fields removed for {0}").format(
                dimension_doc.label
            ),
            alert=True,
            indicator="orange",
        )

    except Exception as e:
        frappe.log_error(
            f"Error deleting dimension fields for {dimension_doc.label}: {str(e)}"
        )


def get_insert_after_field(doctype):
    """Get the field to insert after, based on your DocType structure"""

    if doctype == "Expense Entry":
        # Try to insert in the accounting dimensions section
        preferred_fields = ["accounting_col", "default_cost_center", "default_project"]
        for field in preferred_fields:
            if frappe.db.exists("DocField", {"parent": doctype, "fieldname": field}):
                return field

    elif doctype == "Expense Entry Item":
        # Try to insert after existing dimension fields
        preferred_fields = ["cost_center", "project", "amount"]
        for field in preferred_fields:
            if frappe.db.exists("DocField", {"parent": doctype, "fieldname": field}):
                return field

    return None


def sync_all_accounting_dimensions():
    """Sync all accounting dimensions - useful for initial setup or migration"""

    accounting_dimensions = frappe.get_all(
        "Accounting Dimension", filters={"disabled": 0}, fields=["name"]
    )

    count = 0
    for dimension in accounting_dimensions:
        dimension_doc = frappe.get_doc("Accounting Dimension", dimension.name)
        create_dimension_fields(dimension_doc)
        count += 1

    frappe.db.commit()
    return f"Synced {count} accounting dimensions"


@frappe.whitelist()
def rebuild_dimension_fields():
    """API endpoint to rebuild all dimension fields - for admins"""

    if not frappe.has_permission("Accounting Dimension", "write"):
        frappe.throw(_("Not permitted"))

    result = sync_all_accounting_dimensions()
    return {"message": result}


def get_all_dimension_fieldnames():
    """Get all accounting dimension fieldnames including core ones"""

    # Core dimension fields from DocType
    core_dimensions = {"project": "Project", "cost_center": "Cost Center"}

    # Custom dimension fields
    custom_dimensions = {}
    accounting_dimensions = frappe.get_all(
        "Accounting Dimension", filters={"disabled": 0}, fields=["fieldname", "label"]
    )

    for dim in accounting_dimensions:
        if dim.fieldname not in core_dimensions:
            custom_dimensions[dim.fieldname] = dim.label

    return {**core_dimensions, **custom_dimensions}


@frappe.whitelist()
def get_dimension_info_for_client():
    """Get dimension information for JavaScript"""
    return {
        "all_dimensions": get_all_dimension_fieldnames(),
        "core_dimensions": ["project", "cost_center"],
        "accounting_dimensions": get_accounting_dimensions_for_client(),
    }


def get_accounting_dimensions_for_client():
    """Get all active accounting dimensions for client-side JavaScript"""
    return frappe.get_all(
        "Accounting Dimension",
        filters={"disabled": 0},
        fields=[
            "name",
            "fieldname",
            "label",
            "document_type",
            "mandatory_for_bs",
            "mandatory_for_pl",
        ],
    )
