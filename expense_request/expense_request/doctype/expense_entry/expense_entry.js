// Copyright (c) 2020, Bantoo and contributors
// For license information, please see license.txt

frappe.provide("expense_entry.expense_entry");

function update_totals(frm, cdt, cdn) {
    var items = locals[cdt][cdn];
    var total = 0;
    var quantity = 0;
    frm.doc.expenses.forEach(
        function (items) {
            total += items.amount;
            quantity += 1;
        });
    frm.set_value("total", total);
    refresh_field("total");
    frm.set_value("quantity", quantity);
    refresh_field("quantity");
}

frappe.ui.form.on('Expense Entry Item', {
    amount: function (frm, cdt, cdn) {
        update_totals(frm, cdt, cdn);
    },
    expenses_remove: function (frm, cdt, cdn) {
        update_totals(frm, cdt, cdn);
    },
    expenses_add: function (frm, cdt, cdn) {
        var d = locals[cdt][cdn];

        if ((d.cost_center === "" || typeof d.cost_center == 'undefined')) {

            if (cur_frm.doc.default_cost_center != "" || typeof cur_frm.doc.default_cost_center != 'undefined') {

                d.cost_center = cur_frm.doc.default_cost_center;
                cur_frm.refresh_field("expenses");
            }
        }
    }

});


frappe.ui.form.on('Expense Entry', {
    before_save: function (frm) {

        $.each(frm.doc.expenses, function (i, d) {
            let label = "";

            if ((d.cost_center === "" || typeof d.cost_center == 'undefined')) {

                if (cur_frm.doc.default_cost_center === "" || typeof cur_frm.doc.default_cost_center == 'undefined') {
                    frappe.validated = false;
                    frappe.msgprint("Set a Default Cost Center or specify the Cost Center for expense <strong>No. "
                        + (i + 1) + "</strong>.");
                    return false;
                }
                else {
                    d.cost_center = cur_frm.doc.default_cost_center;
                }
            }
        });

    },
    refresh(frm) {
        //update total and qty when an item is added
    },
    onload(frm) {
        refresh_fields_on_company_change(frm);
    },
    company(frm) {
        refresh_fields_on_company_change(frm);
    }
});


function refresh_fields_on_company_change(frm) {
    frm.set_value("expenses", []);
    frm.set_query("expense_account", 'expenses', () => {
        return {
            filters: [
                ["Account", "root_type", "=", "Expense"],
                ["Account", "is_group", "=", "0"],
                ["Account", "company", "=", frm.doc.company]
            ]
        }
    });
    frm.set_query("cost_center", 'expenses', () => {
        return {
            filters: [
                ["Cost Center", "is_group", "=", "0"],
                ["Cost Center", "company", "=", frm.doc.company]
            ]
        }
    });
    // frm.set_value("custom_department", '');
    // frm.set_query("custom_department", () => {
    //     return {
    //         filters: { company: frm.doc.company }
    //     }
    // });
    frm.set_value("mode_of_payment", '');
    frm.set_query("mode_of_payment", () => {
        return {
            filters: [
                ["Mode of Payment Account", "company", "=", frm.doc.company]
            ]
        }
    });
    frm.set_value("default_project", '');
    frm.set_query("default_project", () => {
        return {
            filters: {
                company: frm.doc.company
            }
        }
    });
    frm.set_value("default_cost_center", '');
    frm.set_query("default_cost_center", () => {
        return {
            filters: [
                ["Cost Center", "is_group", "=", "0"],
                ["Cost Center", "company", "=", frm.doc.company]
            ]
        }
    });
}

