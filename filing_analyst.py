import sqlite3

DB_PATH = "data/red_shift.db"

# Sample extracted passages representing real annual report disclosures (MD&A / Notes)
SAMPLE_FILING_PASSAGES = [
    """Note 34: Contingent Liabilities and Commitments. The Company has issued corporate guarantees 
    amounting to INR 1,245 Crores on behalf of certain overseas subsidiary entities. The statutory 
    auditors have drawn attention to material uncertainty regarding the recoverability of these advances.""",
    
    """Item 4: Shareholding Pattern. As of March 31, 2024, the promoter group holds 3.99% equity shares 
    in the Company, of which 100% of promoter shares remain pledged with financial institutions against 
    borrowings taken by promoter-controlled private entities.""",
    
    """Report on Other Legal and Regulatory Requirements: We draw attention to Note 12 of the standalone 
    financial statements regarding ongoing investigations by regulatory authorities into related party 
    transactions with certain distributor entities."""
]

def grounding_guard_verifier(source_passages, quotation):
    """
    FR-31 & Tech Docs Section 6.3: Verifies that the model-generated quotation 
    exists verbatim inside the supplied source passages.
    """
    if not quotation:
        return False
        
    clean_quote = " ".join(quotation.strip().split()).lower()
    for passage in source_passages:
        clean_passage = " ".join(passage.strip().split()).lower()
        if clean_quote in clean_passage:
            return True
            
    return False

def run_filing_analyst(company_id=1, symbol="ZEEL"):
    print(f"\n--- Running Filing Analyst Agent for {symbol} ---")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Find the latest screening run_id
    cursor.execute("SELECT run_id FROM SCORE_RUN WHERE company_id = ? ORDER BY run_id DESC LIMIT 1;", (company_id,))
    row = cursor.fetchone()
    if not row:
        print("No prior score run found. Run quant_scorer.py first.")
        conn.close()
        return
    run_id = row[0]

    # Target risk themes (FR-27 & Tech Docs Section 6.3)
    mock_model_findings = [
        {
            "theme": "Promoter Share Pledging",
            "severity": "High",
            "finding_text": "Entire promoter holding is encumbered against third-party debt.",
            "quotation": "100% of promoter shares remain pledged with financial institutions"
        },
        {
            "theme": "Contingent Liabilities",
            "severity": "High",
            "finding_text": "Significant corporate guarantees extended to overseas subsidiaries under uncertainty.",
            "quotation": "issued corporate guarantees amounting to INR 1,245 Crores on behalf of certain overseas subsidiary entities"
        },
        {
            "theme": "Going Concern / Auditor Qualification",
            "severity": "High",
            "finding_text": "Fabricated finding test to verify grounding guard rejection.",
            "quotation": "Auditors have declared immediate company insolvency."  # Hallucination test
        }
    ]

    verified_count = 0
    discarded_count = 0

    for finding in mock_model_findings:
        theme = finding["theme"]
        quotation = finding["quotation"]
        severity = finding["severity"]
        finding_text = finding["finding_text"]

        # Run Grounding Guard (FR-31)
        is_verified = grounding_guard_verifier(SAMPLE_FILING_PASSAGES, quotation)

        if is_verified:
            status = "Verified"
            verified_count += 1
            print(f"PASS [Grounding Guard]: {theme} -> Verified quote accepted.")

            # Persist to QUAL_FINDING
            cursor.execute("""
            INSERT INTO QUAL_FINDING (run_id, theme, severity, finding_text, quotation, verification_status)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (run_id, theme, severity, finding_text, quotation, status))

            # Raise Red Flag bound to this evidence
            cursor.execute("""
            INSERT INTO RED_FLAG (run_id, category, flag_type, severity, explanation, evidence_ref)
            VALUES (?, 'Qualitative', ?, ?, ?, ?)
            """, (run_id, theme, severity, finding_text, f"Quotation: \"{quotation}\""))

        else:
            discarded_count += 1
            print(f"REJECTED [Grounding Guard Failed]: {theme} -> Quote not found in source text. Discarded.")

    conn.commit()
    conn.close()
    print(f"\nFiling Analyst finished. Verified & Stored: {verified_count}, Discarded Hallucinations: {discarded_count}\n")

if __name__ == "__main__":
    run_filing_analyst(company_id=1, symbol="ZEEL")