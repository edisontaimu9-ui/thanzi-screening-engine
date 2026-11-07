"""Worker-view wording that depends on decision I20 (D86). Draft pending clinician review (I23).

A MAM child can only be sent to OTP instead of SFP under the HIV rule, so naming the programme in a
worker response would let a knowledgeable reader infer HIV status. Every MAM worker response therefore
carries the same neutral wording, whatever the programme. The real programme is in the audit view only.
"""
from __future__ import annotations

STATUS = "Demonstration only. Built on synthetic data. Not validated on real children."
API_VERSION = "v1"

MAM_ACTION = ("Refer for further assessment of moderate acute malnutrition. "
              "Confirm the programme with your supervisor or clinician before referring.")
MAM_WARNING = "A clinician confirms the programme and admission requirements before referral."
MAM_RULE_CODE = "MAM.REFER"

# Display aliases for the worker view only. Engine codes are unchanged (D82, D86).
RULE_CODE_ALIAS = {"MAM.HIV_OTP": MAM_RULE_CODE, "MAM.SFP": MAM_RULE_CODE}
