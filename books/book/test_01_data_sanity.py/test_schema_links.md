# Schema links


  bank_transactions:
    customer_id -> customers.customer_id
    invoice_id -> invoices.invoice_id
  employees:
    customer_id -> customers.customer_id
    supervisor_id -> employees.employee_id
  help_impressions:
    prev_article_id -> help_articles.article_id
    article_id -> help_articles.article_id
  invoices:
    customer_id -> customers.customer_id
    approver -> employees.employee_id
    processor -> employees.employee_id
    vendor_business_id -> corporate_entities.business_id
  overrides:
    customer_id -> customers.customer_id
    invoice_id -> invoices.invoice_id
  prediction_log:
    customer_id -> customers.customer_id
  rule_revisions:
    customer_id -> customers.customer_id

ok
