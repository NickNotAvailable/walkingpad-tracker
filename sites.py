# Sites to search. "{q}" is replaced with each search term.
# If a site changes its search address, just edit the URL here.
# where: "home" = checked from your Mac (site blocks servers); default is GitHub.
# kind: "marketplace" (new + used, private sellers) or "retailer" (shops, new items).

SEARCH_TERMS = ["walkingpad", "walking pad", "kingsmith"]

SITES = [
    {"name": "MyMarket.ge", "kind": "marketplace",
     "url": "https://mymarket.ge/products/?Keyword={q}", "where": "home"},
    {"name": "SS.ge", "kind": "marketplace",
     "url": "https://ss.ge/ka/sales/list?Query={q}"},
    {"name": "Extra.ge", "kind": "marketplace",
     "url": "https://extra.ge/search?q={q}"},
    {"name": "Zoommer.ge", "kind": "retailer",
     "url": "https://zoommer.ge/search/{q}", "where": "home"},
    {"name": "Elit Electronics (ee.ge)", "kind": "retailer",
     "url": "https://ee.ge/search/{q}", "where": "home"},
    # Metromart.ge: its own search page gives a server error, so it's left out for now.
    {"name": "Megatechnica.ge", "kind": "retailer",
     "url": "https://www.megatechnica.ge/ka/all?title={q}"},
    {"name": "Veli.store", "kind": "retailer",
     "url": "https://veli.store/search?q={q}"},
]
