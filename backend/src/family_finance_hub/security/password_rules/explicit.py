import re

from .schema import PasswordRule


class ExplicitPasswordRuleParser:
    """Parse a small set of unambiguous password instructions without AI."""

    _password = (
        r"(?:密碼|密码|開啟密碼|开启密码|開啟碼|开启码|"
        r"password|passcode)"
    )
    _national_id = (
        r"(?:國民身分證(?:統一)?(?:編號|字號|號碼)?|"
        r"国民身份证(?:统一)?(?:编号|字号|号码)?|"
        r"身分證(?:統一)?(?:編號|字號|號碼)?|"
        r"身份證(?:統一)?(?:編號|字號|號碼)?|"
        r"身分证(?:统一)?(?:编号|字号|号码)?|"
        r"身份证(?:统一)?(?:编号|字号|号码)?|"
        r"national\s*(?:id|identification)(?:\s*(?:number|no\.?))?|"
        r"identity\s*card(?:\s*(?:number|no\.?))?)"
    )
    _password_then_id = re.compile(
        rf"{_password}.{{0,80}}?(?:為|为|是|使用|輸入|输入|採用|采用|use|enter|[:：=])"
        rf"\s*(?:您(?:的)?|你的|your)?\s*{_national_id}",
        re.IGNORECASE | re.DOTALL,
    )
    _id_then_password = re.compile(
        rf"{_national_id}.{{0,50}}?(?:作為|作为|當作|当作|用作|as)\s*(?:附件)?{_password}",
        re.IGNORECASE | re.DOTALL,
    )
    _parenthetical_id = re.compile(
        rf"{_password}\s*[（(]\s*(?:您(?:的)?|你的|your)?\s*{_national_id}",
        re.IGNORECASE,
    )
    _open_statement_then_id = re.compile(
        rf"(?:開啟|开启)\s*(?:電子|电子)?(?:帳單|账单|附件)\s*"
        rf"(?:請|请)?(?:輸入|输入)\s*(?:正卡人|持卡人|您(?:的)?|你的)?\s*{_national_id}",
        re.IGNORECASE,
    )
    _other_source = re.compile(
        r"生日|出生(?:日期|年月日)?|birth(?:day|\s*date)?|date\s+of\s+birth|\bDOB\b",
        re.IGNORECASE,
    )
    _domestic_customer = re.compile(
        r"本國籍|本国籍|台灣籍|台湾籍|Taiwan(?:ese)?\s+customers?",
        re.IGNORECASE,
    )
    _foreign_customer = re.compile(
        r"外籍|外國籍|外国籍|foreign\s+customers?",
        re.IGNORECASE,
    )
    _birthday_yyyymmdd = re.compile(
        r"(?:生日|出生(?:日期|年月日)?|birth(?:day|\s*date)?|date\s+of\s+birth|\bDOB\b)"
        r".{0,32}?(?:YYYYMMDD|西元.{0,8}?8\s*(?:碼|码|digits?))",
        re.IGNORECASE | re.DOTALL,
    )
    _partial_id = re.compile(
        r"(?:末|後|后|最後|最后|前|首)\s*(?:[一二三四五六七八九十\d]+\s*)?(?:位|碼|码)|"
        r"\b(?:prefix|suffix|first|last)\b|\b\d+\s*digits?\b",
        re.IGNORECASE,
    )
    _combination = re.compile(
        r"(?:\+|加上|再加|搭配|組合|组合|串接|拼接|followed\s+by|\bplus\b)",
        re.IGNORECASE,
    )
    _upper = re.compile(
        r"(?:英文字母|英文|字母|letter).{0,12}(?:為|为|用|使用|轉為|转为|請用|请用|需用|須用|须用)?"
        r"\s*(?:大寫|大写|uppercase|upper\s*case)|"
        r"(?:大寫|大写|uppercase|upper\s*case).{0,12}(?:英文字母|英文|字母|letter)",
        re.IGNORECASE,
    )
    _lower = re.compile(
        r"(?:英文字母|英文|字母|letter).{0,12}(?:為|为|用|使用|轉為|转为|請用|请用|需用|須用|须用)?"
        r"\s*(?:小寫|小写|lowercase|lower\s*case)|"
        r"(?:小寫|小写|lowercase|lower\s*case).{0,12}(?:英文字母|英文|字母|letter)",
        re.IGNORECASE,
    )

    def parse(self, instruction: str) -> PasswordRule | None:
        text = instruction.strip()
        if not text or not (
            self._password_then_id.search(text)
            or self._id_then_password.search(text)
            or self._parenthetical_id.search(text)
            or self._open_statement_then_id.search(text)
        ):
            return None
        upper = bool(self._upper.search(text))
        lower = bool(self._lower.search(text))
        if upper and lower:
            return None
        if (
            self._partial_id.search(text)
            or self._combination.search(text)
        ):
            return None

        letter_case = "upper" if upper else "lower" if lower else "preserve"
        if self._other_source.search(text):
            if not (
                self._domestic_customer.search(text)
                and self._foreign_customer.search(text)
                and self._birthday_yyyymmdd.search(text)
            ):
                return None
            return PasswordRule.model_validate({
                "version": 1,
                "status": "ambiguous",
                "candidates": [
                    self._national_id_candidate(letter_case),
                    self._birthday_candidate(),
                ],
            })

        return PasswordRule.model_validate({
            "version": 1,
            "status": "resolved",
            "candidates": [self._national_id_candidate(letter_case)],
        })

    @staticmethod
    def _national_id_candidate(letter_case: str) -> dict[str, object]:
        return {
            "parts": [{
                "source": "national_id",
                "transform": "full",
                "start": None,
                "length": None,
                "date_format": None,
                "case": letter_case,
            }],
            "separator": "",
        }

    @staticmethod
    def _birthday_candidate() -> dict[str, object]:
        return {
            "parts": [{
                "source": "birthday",
                "transform": "date_format",
                "start": None,
                "length": None,
                "date_format": "YYYYMMDD",
                "case": "preserve",
            }],
            "separator": "",
        }
