import erpnext
import frappe
from erpnext.accounts.utils import get_account_currency
from erpnext.setup.utils import get_exchange_rate as _get_exchange_rate
from frappe import _, utils
from frappe.utils import flt


def get_accounting_dimensions():
	"""Get all active accounting dimensions from the system"""
	return frappe.get_all(
		"Accounting Dimension",
		filters={"disabled": 0},
		fields=["name", "fieldname", "label", "document_type"],
	)



def setup(expense_entry, method):
	"""Enhanced setup function with dynamic accounting dimensions support"""

	# Get all accounting dimensions
	#

	accounting_dimensions = get_accounting_dimensions()
	company_currency = erpnext.get_company_currency(expense_entry.company)

	# Add expenses up and set the total field
	# Add default accounting dimensions to expense items

	total = 0
	count = 0
	expense_items = []

	for detail in expense_entry.expenses:
		count += 1

		detail.currency = get_account_currency(detail.expense_account)

		if not detail.amount:
			if not detail.exchange_rate:
				detail.exchange_rate =  _get_exchange_rate(detail.currency, company_currency)
			detail.amount = flt(detail.amount_in_account_currency) * detail.exchange_rate

		total += detail.amount

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

	make_journal_entry(expense_entry, company_currency)


@frappe.whitelist()
def initialise_journal_entry(expense_entry_name):
	# make JE from javascript form Make JE button
	expense_entry = frappe.get_doc("Expense Entry", expense_entry_name)
	company_currency = erpnext.get_company_currency(expense_entry.company)


	make_journal_entry(expense_entry, company_currency)


def make_journal_entry(expense_entry, company_currency):

	if expense_entry.status != "Approved":
		return

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
		if detail.currency != company_currency:
			use_multi_currency = True

		account_detail = {
			"account": detail.expense_account,
			"account_currency": detail.currency,
			"exchange_rate": flt(detail.exchange_rate) or 1.0,
			"debit_in_account_currency": flt(detail.amount_in_account_currency),
			"user_remark": str(detail.description),
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

	pay_currency = get_account_currency(pay_account)
	pay_rate = _get_exchange_rate(pay_currency, company_currency)


	if pay_currency != company_currency:
		use_multi_currency = True

	# Credit account entry with default accounting dimensions
	credit_account_detail = {
		"account": pay_account,
		"account_currency": pay_currency,
		"exchange_rate": pay_rate,
		"credit_in_account_currency": flt(expense_entry.total / pay_rate, precision=2),
		"user_remark": str(detail.description),
	}
	diff = flt(expense_entry.total - flt(flt(expense_entry.total / pay_rate, precision=2) * pay_rate, precision=2), precision=2)
	if diff != 0:
		# Fetch a rounding account from Company defaults or use a placeholder
		rounding_account = frappe.get_cached_value('Company', expense_entry.company, 'round_off_account')
		if not rounding_account:
			frappe.throw(_("Please set a Round Off Account in Company {0}").format(expense_entry.company))

		accounts.append({
			"account": rounding_account,
			"account_currency": company_currency,
			"exchange_rate": 1.0,
			"credit_in_account_currency": diff if diff > 0 else 0,
			"debit_in_account_currency": abs(diff) if diff < 0 else 0,
			"user_remark": _("Rounding adjustment for multi-currency conversion")
		})

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
			# "title": expense_entry.name,
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"posting_date": expense_entry.posting_date,
			"company": expense_entry.company,
			"accounts": accounts,
			"user_remark": expense_entry.remarks,
			"mode_of_payment": expense_entry.mode_of_payment,
			"cheque_date": expense_entry.clearance_date,
			"reference_date": expense_entry.clearance_date,
			"multi_currency": 1 if use_multi_currency else 0,
			"cheque_no": expense_entry.payment_reference,
			"pay_to_recd_from": expense_entry.payment_to,
			"bill_no": expense_entry.name,
		}
	)

	user = frappe.get_doc("User", frappe.session.user)
	full_name = str(user.first_name) + " " + str(user.last_name)
	expense_entry.db_set("approved_by", full_name)

	# je.save()
	je.insert()
	je.submit()


@frappe.whitelist()
def get_accounting_dimensions_for_client():
	"""API endpoint to get accounting dimensions for client-side JavaScript"""
	return get_accounting_dimensions()

