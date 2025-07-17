# -*- coding: utf-8 -*-
# Copyright (c) 2020, Bantoo and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class ExpenseEntry(Document):
    def on_cancel(self):
        # Find and cancel linked journal entries
        je_list = frappe.get_all("Journal Entry", 
            filters={
                "bill_no": self.name,
                "docstatus": 1
            })

        for je in je_list:
            journal_entry = frappe.get_doc("Journal Entry", je.name)
            if journal_entry.docstatus == 1:
                # Cancel journal entry
                journal_entry.cancel()
                frappe.msgprint(f"Journal Entry {journal_entry.name} has been cancelled.")

                # Now delete the journal entry
                frappe.delete_doc("Journal Entry", journal_entry.name, force=1)
                frappe.msgprint(f"Journal Entry {journal_entry.name} has been deleted.")
