"""HMDA codes and loan filters shared by clean_hmda.py and the stress index.

Kept in one place so the Phase 2 layers and the Phase 4 index can't drift
apart on what "a qualifying loan" or "DTI above 43%" means. All codes are from
the HMDA Filing Instructions Guide; the CSVs are read as text (all_varchar),
so codes are compared as strings.
"""

# Loan-level filters (SPEC: HMDA layers, DECISIONS 013), minus action_taken,
# which differs between originations and applications.
BASE_FILTERS = """
    loan_purpose = '1'          -- home purchase
    AND lien_status = '1'       -- first lien
    AND occupancy_type = '1'    -- principal residence
    -- Exclude open-end lines of credit and reverse mortgages ('1').
    -- '1111' means the lender is exempt from reporting the flag, not that
    -- the loan is open-end or reverse, so those loans stay in.
    AND open_end_line_of_credit IS DISTINCT FROM '1'
    AND reverse_mortgage IS DISTINCT FROM '1'
"""

ORIGINATED = "action_taken = '1'"  # loan originated
FILTERS = f"{ORIGINATED} AND {BASE_FILTERS}"

# Applications for the DTI denial rate: originated (1), approved but not
# accepted (2), denied (3). Withdrawn, incomplete, purchased loans and
# preapproval requests (4-8) aren't decisions on a purchase application.
APPLICATION_ACTIONS = ["1", "2", "3"]
DENIED = "3"
# denial_reason_1-4: 1 = debt-to-income ratio. 10 = not applicable, 1111 = exempt.
DENIAL_DTI = "1"
DENIAL_COLUMNS = ["denial_reason_1", "denial_reason_2", "denial_reason_3", "denial_reason_4"]

# debt_to_income_ratio is reported in bins below 36% and above 49%, and as
# whole-number strings from 36 to 49 in between. "Above 43%" is therefore the
# strings 44-49 plus the two top bins. '43' itself is not above 43.
DTI_OVER_43 = ["44", "45", "46", "47", "48", "49", "50%-60%", ">60%"]

# Every value debt_to_income_ratio can take other than 'NA' and 'Exempt'.
# Listing them makes an unexpected new code count as invalid, not silently as
# "not over 43".
DTI_VALID = ["<20%", "20%-<30%", "30%-<36%"] + [str(i) for i in range(36, 50)] + ["50%-60%", ">60%"]

CLTV_THRESHOLD = 90  # percent

# loan_type: 1 conventional, 2 FHA, 3 VA, 4 USDA/RHS. The CLTV measures count
# conventional loans only (DECISIONS 019, 021): FHA, VA and USDA loans are
# above 90% CLTV by program design (3.5% or zero down).
CONVENTIONAL = "1"
GOVERNMENT = ["2", "3", "4"]


def sql_list(values):
    return ", ".join(f"'{v}'" for v in values)


def dti_over_43_sql(col="debt_to_income_ratio"):
    """SQL: TRUE/FALSE for a valid DTI code, NULL for NA, Exempt or unknown."""
    return (f"CASE WHEN {col} IN ({sql_list(DTI_VALID)}) "
            f"THEN {col} IN ({sql_list(DTI_OVER_43)}) END")


def denied_for_dti_sql():
    """SQL: TRUE when debt-to-income is any of the four denial reasons.

    Unused reason columns are empty (NULL), and `x IN (..., NULL)` is NULL
    rather than FALSE when nothing matches, hence the COALESCE.
    """
    return f"COALESCE('{DENIAL_DTI}' IN ({', '.join(DENIAL_COLUMNS)}), FALSE)"
