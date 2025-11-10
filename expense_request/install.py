# -*- coding: utf-8 -*-
# Copyright (c) 2025, Bantoo and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def after_install():
    """
    Runs after app installation and migration.
    Syncs accounting dimension fields dynamically.
    """
    sync_accounting_dimensions()


def sync_accounting_dimensions():
    """Dynamically add accounting dimension fields to Expense Entry doctypes"""

    # Get all active accounting dimensions
    accounting_dimensions = frappe.get_all(
        "Accounting Dimension",
        filters={"disabled": 0},
        fields=["name", "fieldname", "label", "document_type"],
    )

    # Track which dimensions we already have as default fields
    existing_default_fields = ["default_project", "default_cost_center"]
    existing_item_fields = ["project", "cost_center"]

    for dimension in accounting_dimensions:
        fieldname = dimension.fieldname
        label = dimension.label
        document_type = dimension.document_type

        # Skip if we already have these as default fields in the DocType
        default_fieldname = f"default_{fieldname}"
        if default_fieldname in existing_default_fields:
            continue

        # Add default dimension field to parent Expense Entry (in Accounting Dimensions section)
        if not frappe.db.exists(
            "Custom Field", {"dt": "Expense Entry", "fieldname": default_fieldname}
        ):
            create_custom_field(
                "Expense Entry",
                {
                    "fieldname": default_fieldname,
                    "label": f"Default {label}",
                    "fieldtype": "Link",
                    "options": document_type,
                    "insert_after": "accounting_col",  # Insert in the accounting dimensions section
                    "in_list_view": 0,
                    "in_standard_filter": 1,
                    "reqd": 0,
                    "description": f"Applies to all expenses below unless specified differently",
                },
            )
            print(f"Created default field for {label}")

        # Skip if we already have these as fields in the child table
        if fieldname in existing_item_fields:
            continue

        # Add dimension field to child table Expense Entry Item
        if not frappe.db.exists(
            "Custom Field", {"dt": "Expense Entry Item", "fieldname": fieldname}
        ):
            create_custom_field(
                "Expense Entry Item",
                {
                    "fieldname": fieldname,
                    "label": label,
                    "fieldtype": "Link",
                    "options": document_type,
                    "insert_after": "cost_center",  # Insert after existing dimensions
                    "in_list_view": 1,
                    "reqd": (
                        1 if dimension.mandatory_for_pl else 0
                    ),  # Set required based on dimension settings
                    "columns": 2,
                },
            )
            print(f"Created item field for {label}")

    # Add a section break if we have additional dimensions
    additional_dimensions = [
        d
        for d in accounting_dimensions
        if f"default_{d.fieldname}" not in existing_default_fields
    ]

    if additional_dimensions and not frappe.db.exists(
        "Custom Field",
        {"dt": "Expense Entry", "fieldname": "additional_dimensions_section"},
    ):
        create_custom_field(
            "Expense Entry",
            {
                "fieldname": "additional_dimensions_section",
                "label": "Additional Accounting Dimensions",
                "fieldtype": "Section Break",
                "insert_after": "accounting_col",
                "collapsible": 1,
            },
        )
        print("Created additional dimensions section")

    frappe.db.commit()
    print(
        f"Synced {len(accounting_dimensions)} accounting dimensions to Expense Entry."
    )
