"""Small, versioned local rules for explicit spending purposes, not product guesses."""
from dataclasses import dataclass
from hashlib import sha256
import json
import re


VERSION = "2026-10-01.2"


@dataclass(frozen=True)
class BuiltinRule:
    id: str
    code: str
    pattern: str
    reason: str


RULES = (
    BuiltinRule("uber_eats", "food", r"UBER[ *-]?EATS(?:[ *./-].*)?", "明示外送服務"),
    BuiltinRule("netflix", "entertainment", r"NETFLIX(?:[ *./-].*)?", "明示影音訂閱"),
    BuiltinRule("chatgpt_subscription", "entertainment", r"OPENAI \*CHATGPT SUBSCR(?: OPENAI\.COM(?: US)?)?", "明示數位服務訂閱"),
    BuiltinRule("high_speed_rail", "transport", r"(?:台灣高鐵|臺灣高鐵|高鐵車票)(?:[ -].*)?", "明示高鐵交通"),
    BuiltinRule("metro", "transport", r"(?:A- )?(?:台北捷運|臺北捷運|臺北大眾捷運股份有限公司|桃園捷運|高雄捷運|捷運車票)(?:[ -].*)?", "明示捷運交通"),
    BuiltinRule("statement_dining", "food", r"(?:A- )?(?:101美食街|三新奧特萊斯 林口I館-餐飲|小島泰式料理|瑪莎拉印度餐廳(?:-[\u4e00-\u9fff]+店)?|阿義師的大茶壺茶餐廳|洋城義大利餐酒館內湖店)", "明示餐飲服務"),
    BuiltinRule("fuel", "transport", r"(?:A- )?(?:[\u4e00-\u9fff]{1,20}加油站|車容坊元泰站-自助加油|中油-基隆路站\(D2144\))", "明示加油服務"),
    BuiltinRule("parking", "transport", r"停車費(?:[ -].*)?", "明示停車費"),
    BuiltinRule("ebook", "books", r"(?:電子書|電子書購買|EBOOK PURCHASE)(?:[ -].*)?", "明示電子書購買"),
    BuiltinRule("tuition", "education", r"(?:學費|課程費|課程學費|TUITION)(?:[ -].*)?", "明示課程或學費"),
    BuiltinRule("insurance_premium", "insurance", r"(?:保險費|保險保費|INSURANCE PREMIUM)(?:[ -].*)?", "明示保險保費"),
    BuiltinRule("medical", "health", r"(?:診所醫療費|醫院醫療費|門診醫療費)(?:[ -].*)?", "明示醫療支出"),
    BuiltinRule("air_ticket", "travel", r"(?:航空機票|機票費|AIRLINE TICKET)(?:[ -].*)?", "明示航空機票"),
)
COMPILED = tuple((rule, re.compile(rule.pattern)) for rule in RULES)
FINGERPRINT = sha256(json.dumps({"version": VERSION, "rules": [
    (rule.id, rule.code, rule.pattern, rule.reason) for rule in RULES
]}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def match_builtin(merchant_key: str) -> BuiltinRule | None:
    return next((rule for rule, pattern in COMPILED if pattern.fullmatch(merchant_key)), None)
