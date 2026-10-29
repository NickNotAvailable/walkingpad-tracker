# Sites to search. "{q}" is replaced with each search term.
# If a site changes its search address, just edit the URL here.
# where: "home" = checked from your Mac (site blocks servers); default is GitHub.
# kind: "marketplace" (new + used, private sellers) or "retailer" (shops, new items).

SEARCH_TERMS = ["walkingpad", "walking pad", "kingsmith"]

SITES = [
    {"name": "MyMarket.ge", "kind": "marketplace",
     "url": "https://www.mymarket.ge/ka/search/?Keyword={q}", "where": "home"},
    {"name": "SS.ge", "kind": "marketplace",
     "url": "https://ss.ge/ka/search?query={q}"},
    {"name": "Extra.ge", "kind": "marketplace",
     "url": "https://extra.ge/search?q={q}"},
    {"name": "Zoommer.ge", "kind": "retailer",
     "url": "https://zoommer.ge/ka/search?q={q}", "where": "home"},
    {"name": "Alta.ge", "kind": "retailer",
     "url": "https://alta.ge/search?q={q}", "where": "home"},
    {"name": "Elit Electronics (ee.ge)", "kind": "retailer",
     "url": "https://ee.ge/search?q={q}", "where": "home"},
    {"name": "Metromart.ge", "kind": "retailer",
     "url": "https://metromart.ge/shop/search?q={q}"},
    {"name": "Megatechnica.ge", "kind": "retailer",
     "url": "https://megatechnica.ge/ge/search?q={q}"},
    {"name": "Veli.store", "kind": "retailer",
     "url": "https://veli.store/search?q={q}"},
]
