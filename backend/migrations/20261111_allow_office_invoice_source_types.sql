BEGIN;

ALTER TABLE invoices
    DROP CONSTRAINT IF EXISTS invoices_source_type_check;

ALTER TABLE invoices
    ADD CONSTRAINT invoices_source_type_check
    CHECK (source_type IN ('pdf', 'docx', 'xlsx', 'xls', 'csv', 'manual', 'demo'));

COMMIT;
