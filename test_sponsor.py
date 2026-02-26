from dotenv import load_dotenv
load_dotenv()

from app.services.search.yandex_search import search_organization_info, format_sponsor_field

info = search_organization_info("ООО «Фармстандарт-Лексредства»", "Россия")

print("=== RAW ANSWER ===")
print(info["raw_answer"])
print()
print("=== PARSED ===")
print("address:", repr(info["address"]))
print("postal:", repr(info["postal_code"]))
print("phone:", repr(info["phone"]))
print()
print("=== FORMATTED ===")
print(format_sponsor_field(info))