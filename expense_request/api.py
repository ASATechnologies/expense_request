import frappe
from frappe import _
from frappe import utils


def get_accounting_dimensions():
    """Get all active accounting dimensions from the system"""
    return frappe.get_all(
        "Accounting Dimension",
        filters={"disabled": 0},
        fields=["name", "fieldname", "label", "document_type"],
    )


def get_accounting_dimension_filters(dimension_doc, company):
    """Get filters for accounting dimension based on its document type"""
    filters = []

    if dimension_doc.document_type == "Cost Center":
        filters = [
            ["Cost Center", "is_group", "=", "0"],
            ["Cost Center", "company", "=", company],
        ]
    elif dimension_doc.document_type == "Project":
        filters = [
            ["Project", "status", "!=", "Cancelled"],
            ["Project", "company", "=", company],
        ]
    else:
        # Generic filters for other document types
        filters = [[dimension_doc.document_type, "disabled", "!=", 1]]

        # Add company filter if the document type has a company field
        if frappe.db.has_column(dimension_doc.document_type, "company"):
            filters.append([dimension_doc.document_type, "company", "=", company])

    return filters


def setup(expense_entry, method):
    """Enhanced setup function with dynamic accounting dimensions support"""

    # Get all accounting dimensions
    #

    accounting_dimensions = get_accounting_dimensions()

    # Add expenses up and set the total field
    # Add default accounting dimensions to expense items

    total = 0
    count = 0
    expense_items = []

    for detail in expense_entry.expenses:
        total += float(detail.amount)
        count += 1

        # Handle all accounting dimensions dynamically
        for dimension in accounting_dimensions:
            fieldname = dimension.fieldname
            default_fieldname = f"default_{fieldname}"

            # Set default dimension values if not already set
            if not getattr(detail, fieldname, None) and getattr(
                expense_entry, default_fieldname, None
            ):
                setattr(detail, fieldname, getattr(expense_entry, default_fieldname))

        expense_items.append(detail)

    expense_entry.expenses = expense_items
    expense_entry.total = total
    expense_entry.quantity = count

    make_journal_entry(expense_entry)


@frappe.whitelist()
def initialise_journal_entry(expense_entry_name):
    # make JE from javascript form Make JE button

    make_journal_entry(frappe.get_doc("Expense Entry", expense_entry_name))


def make_journal_entry(expense_entry):

    if expense_entry.status == "Approved":

        # Check for duplicates
        if frappe.db.exists(
            {"doctype": "Journal Entry", "bill_no": expense_entry.name}
        ):
            frappe.throw(
                title="Error",
                msg="Journal Entry {} already exists.".format(expense_entry.name),
            )

        # Get all accounting dimensions
        accounting_dimensions = get_accounting_dimensions()

        # Preparing the JE: convert expense_entry details into je account details
        accounts = []

        for detail in expense_entry.expenses:

            account_detail = {
                "debit_in_account_currency": float(detail.amount),
                "user_remark": str(detail.description),
                "account": detail.expense_account,
            }

            project_value = getattr(detail, "project", None)
            if project_value:
                account_detail["project"] = project_value

            cost_center_value = getattr(detail, "cost_center", None)
            if cost_center_value:
                account_detail["cost_center"] = cost_center_value

            # Add all accounting dimensions dynamically
            for dimension in accounting_dimensions:
                fieldname = dimension.fieldname
                dimension_value = getattr(detail, fieldname, None)
                if dimension_value:
                    account_detail[fieldname] = dimension_value

            accounts.append(account_detail)

        # Finally add the payment account detail
        pay_account = ""

        if expense_entry.mode_of_payment != "Cash" and (
            not expense_entry.payment_reference or not expense_entry.clearance_date
        ):
            frappe.throw(
                title="Enter Payment Reference",
                msg="Payment Reference and Date are Required for all non-cash payments.",
            )
        else:
            expense_entry.clearance_date = ""
            expense_entry.payment_reference = ""

        pay_account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": expense_entry.mode_of_payment, "company": expense_entry.company},
            "default_account",
        )

        if not pay_account or pay_account == "":
            frappe.throw(
                title="Error", msg="The selected Mode of Payment has no linked account."
            )

        # Credit account entry with default accounting dimensions
        credit_account_detail = {
            "credit_in_account_currency": float(expense_entry.total),
            "user_remark": str(detail.description),
            "account": pay_account,
        }

        project_value = getattr(detail, "project", None)
        if project_value:
            credit_account_detail["project"] = project_value

        # Add default accounting dimensions to credit entry
        for dimension in accounting_dimensions:
            fieldname = dimension.fieldname
            default_fieldname = f"default_{fieldname}"
            default_value = getattr(expense_entry, default_fieldname, None)
            if default_value:
                credit_account_detail[fieldname] = default_value

        accounts.append(credit_account_detail)

        # Create the journal entry
        je = frappe.get_doc(
            {
                "title": expense_entry.name,
                "doctype": "Journal Entry",
                "voucher_type": "Journal Entry",
                "posting_date": expense_entry.posting_date,
                "company": expense_entry.company,
                "accounts": accounts,
                "user_remark": expense_entry.remarks,
                "mode_of_payment": expense_entry.mode_of_payment,
                "cheque_date": expense_entry.clearance_date,
                "reference_date": expense_entry.clearance_date,
                "cheque_no": expense_entry.payment_reference,
                "pay_to_recd_from": expense_entry.payment_to,
                "bill_no": expense_entry.name,
            }
        )

        user = frappe.get_doc("User", frappe.session.user)
        full_name = str(user.first_name) + " " + str(user.last_name)
        expense_entry.db_set("approved_by", full_name)

        je.insert()
        je.submit()


@frappe.whitelist()
def get_accounting_dimensions_for_client():
    """API endpoint to get accounting dimensions for client-side JavaScript"""
    return get_accounting_dimensions()


@frappe.whitelist()
def get_dimension_filters(dimension_name, company):
    """API endpoint to get filters for a specific accounting dimension"""
    dimension_doc = frappe.get_doc("Accounting Dimension", dimension_name)
    return get_accounting_dimension_filters(dimension_doc, company)
