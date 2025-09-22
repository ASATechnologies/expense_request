// Copyright (c) 2020, Bantoo and contributors
// For license information, please see license.txt

frappe.provide("expense_entry.expense_entry");

let accounting_dimensions = [];

// ---- totals ----
function update_totals(frm) {
    let total = 0;
    let quantity = 0;

    if (Array.isArray(frm.doc.expenses)) {
        frm.doc.expenses.forEach(function(row) {
            total += Number(row.amount || 0);
            quantity += 1;
        });
    }

    frm.set_value("total", total);
    frm.set_value("quantity", quantity);
    frm.refresh_field("total");
    frm.refresh_field("quantity");
}

// ---- load dimensions from server (robust) ----
function load_accounting_dimensions(frm) {
    // avoid duplicate parallel loads
    if (frm._loading_accounting_dimensions) return;
    frm._loading_accounting_dimensions = true;

    // if no company set yet, clear and return
    if (!frm.doc.company) {
        accounting_dimensions = [];
        setup_dimension_queries(frm);
        frm._loading_accounting_dimensions = false;
        return;
    }

    frappe.call({
        method: "expense_request.api.get_accounting_dimensions_for_client",
        args: { company: frm.doc.company },           // pass company explicitly
        freeze: true,
        freeze_message: __("Loading accounting dimensions..."),
        callback: function(r) {
            frm._loading_accounting_dimensions = false;
            if (r && !r.exc && r.message) {
                accounting_dimensions = r.message || [];
                setup_dimension_queries(frm);
            } else {
                accounting_dimensions = [];
                console.error("Could not load accounting dimensions", r && r.exc ? r.exc : r);
                frappe.msgprint({
                    title: __("Error"),
                    message: __("Could not load accounting dimensions. Check server logs or ensure the API is whitelisted."),
                    indicator: "red"
                });
                setup_dimension_queries(frm); // keep queries consistent (will be empty)
            }
        }
    }).catch(function(err) {
        frm._loading_accounting_dimensions = false;
        accounting_dimensions = [];
        console.error("Error fetching accounting dimensions:", err);
        frappe.msgprint({
            title: __("Error"),
            message: __("Error fetching accounting dimensions. See console for details."),
            indicator: "red"
        });
        setup_dimension_queries(frm);
    });
}

// ---- set queries based on loaded dimensions ----
function setup_dimension_queries(frm) {
    // if no dimensions, we still set no-op queries to avoid past problems
    if (!Array.isArray(accounting_dimensions)) accounting_dimensions = [];

    accounting_dimensions.forEach(function(dimension) {
        if (!dimension.fieldname) return;

        // child table query: field in rows of 'expenses' table
        frm.set_query(dimension.fieldname, 'expenses', function(doc, cdt, cdn) {
            return get_dimension_query_filters(dimension, doc.company || frm.doc.company);
        });

        // default dimension field on parent (named default_<fieldname>)
        let default_fieldname = `default_${dimension.fieldname}`;
        frm.set_query(default_fieldname, function(doc) {
            return get_dimension_query_filters(dimension, doc.company || frm.doc.company);
        });
    });
}

// ---- build filters for a single dimension ----
function get_dimension_query_filters(dimension, company) {
    // ensure company is defined (server-side filters may require this)
    company = company || "";

    if (dimension.document_type === "Cost Center") {
        return {
            filters: [
                ["Cost Center", "is_group", "=", "0"],
                ["Cost Center", "company", "=", company]
            ]
        };
    } else if (dimension.document_type === "Project") {
        return {
            filters: [
                ["Project", "status", "!=", "Cancelled"],
                ["Project", "company", "=", company]
            ]
        };
    } else {
        // Generic filters for other doc types (disabled + company)
        return {
            filters: [
                // [dimension.document_type, "disabled", "!=", 1],
                [dimension.document_type, "company", "=", company]
            ]
        };
    }
}

// ---- when a new child row is added, set defaults from parent ----
function set_default_dimensions_on_add(frm, cdt, cdn) {
    const row = locals[cdt] && locals[cdt][cdn];
    if (!row) return;

    accounting_dimensions.forEach(function(dimension) {
        let fieldname = dimension.fieldname;
        let default_fieldname = `default_${fieldname}`;

        if ((!row[fieldname] || row[fieldname] === "") && frm.doc[default_fieldname]) {
            // set child row value safely
            frappe.model.set_value(cdt, cdn, fieldname, frm.doc[default_fieldname]);
        }
    });

    frm.refresh_field("expenses");
}

// ---- validate mandatory dimensions (kept but safe) ----
function validate_mandatory_dimensions(frm) {
    let validation_passed = true;

    frm.doc.expenses && frm.doc.expenses.forEach(function(expense, index) {
        accounting_dimensions.forEach(function(dimension) {
            let fieldname = dimension.fieldname;
            let default_fieldname = `default_${fieldname}`;

            // Example check: if dimension.mandatory_for_pl is true -> ensure set
            if (dimension.mandatory_for_pl) {
                if (!expense[fieldname] && !frm.doc[default_fieldname]) {
                    frappe.validated = false;
                    validation_passed = false;
                    frappe.msgprint({
                        title: __("Mandatory Field Missing"),
                        message: `${dimension.label} is mandatory. Please set a default ${dimension.label} or specify it for expense <strong>No. ${index + 1}</strong>.`,
                        indicator: "red"
                    });
                    return false;
                } else if (!expense[fieldname] && frm.doc[default_fieldname]) {
                    frappe.model.set_value(expense.doctype, expense.name, fieldname, frm.doc[default_fieldname]);
                }
            }
        });
    });

    return validation_passed;
}

// ---- clear defaults on company change ----
function clear_default_dimensions(frm) {
    accounting_dimensions.forEach(function(dimension) {
        let default_fieldname = `default_${dimension.fieldname}`;
        frm.set_value(default_fieldname, '');
    });
}

// ---- event handlers ----
frappe.ui.form.on('Expense Entry Item', {
    amount: function(frm, cdt, cdn) {
        update_totals(frm);
    },

    expenses_remove: function(frm, cdt, cdn) {
        update_totals(frm);
    },

    // Note: depending on Frappe version, this event name may need to be on the parent doctype:
    // frappe.ui.form.on('Expense Entry', { expenses_add: function(frm, cdt, cdn) { ... } })
    expenses_add: function(frm, cdt, cdn) {
        set_default_dimensions_on_add(frm, cdt, cdn);
    }
});

frappe.ui.form.on('Expense Entry', {
    before_save: function(frm) {
        if (!validate_mandatory_dimensions(frm)) {
            frappe.validated = false;
            return false;
        }
    },

    refresh: function(frm) {
        // only load if company is defined
        if ((!accounting_dimensions || accounting_dimensions.length === 0) && frm.doc.company) {
            load_accounting_dimensions(frm);
        }
    },

    onload: function(frm) {
        if (frm.doc.company) {
            load_accounting_dimensions(frm);
        }
        set_queries(frm);
    },

    company: function(frm) {
        // company changed -> reload dims and clear defaults
        if (frm.doc.company) {
            load_accounting_dimensions(frm);
            set_queries(frm);
        } else {
            accounting_dimensions = [];
            setup_dimension_queries(frm);
        }
        clear_default_dimensions(frm);
    }
});

// ---- queries for other fields ----
function set_queries(frm) {
    frm.set_query("expense_account", 'expenses', function() {
        return {
            filters: [
                ["Account", "root_type", "=", "Expense"],
                ["Account", "is_group", "=", "0"],
                ["Account", "company", "=", frm.doc.company]
            ]
        };
    });

    // dimension queries are set in setup_dimension_queries() after load
}
