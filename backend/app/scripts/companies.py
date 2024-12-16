"""Company information for scraping."""

from typing import Dict, List

COMPANIES = {
    "Technology": {
        "Large Cap": [
            {
                "domain": "apple.com",
                "name": "Apple Inc.",
                "symbol": "AAPL",
                "cik": "320193",
            },
            {
                "domain": "microsoft.com",
                "name": "Microsoft Corporation",
                "symbol": "MSFT",
                "cik": "789019",
            },
            {
                "domain": "nvidia.com",
                "name": "NVIDIA Corporation",
                "symbol": "NVDA",
                "cik": "1045810",
            },
            {
                "domain": "broadcom.com",
                "name": "Broadcom Inc.",
                "symbol": "AVGO",
                "cik": "1730168",
            },
            {
                "domain": "cisco.com",
                "name": "Cisco Systems",
                "symbol": "CSCO",
                "cik": "858877",
            },
            {
                "domain": "salesforce.com",
                "name": "Salesforce Inc.",
                "symbol": "CRM",
                "cik": "1108524",
            },
            {
                "domain": "oracle.com",
                "name": "Oracle Corporation",
                "symbol": "ORCL",
                "cik": "1341439",
            },
        ],
        "Mid Cap": [
            {
                "domain": "amd.com",
                "name": "Advanced Micro Devices",
                "symbol": "AMD",
                "cik": "2488",
            },
            {
                "domain": "servicenow.com",
                "name": "ServiceNow",
                "symbol": "NOW",
                "cik": "1373715",
            },
            {
                "domain": "synopsys.com",
                "name": "Synopsys Inc.",
                "symbol": "SNPS",
                "cik": "883241",
            },
            {
                "domain": "cadence.com",
                "name": "Cadence Design Systems",
                "symbol": "CDNS",
                "cik": "813672",
            },
            {
                "domain": "splunk.com",
                "name": "Splunk Inc.",
                "symbol": "SPLK",
                "cik": "1353283",
            },
        ],
        "Small Cap": [
            {
                "domain": "digitalocean.com",
                "name": "DigitalOcean Holdings",
                "symbol": "DOCN",
                "cik": "1581584",
            },
            {
                "domain": "gitlab.com",
                "name": "GitLab Inc.",
                "symbol": "GTLB",
                "cik": "1653482",
            },
            {
                "domain": "hashicorp.com",
                "name": "HashiCorp Inc.",
                "symbol": "HCP",
                "cik": "1856356",
            },
        ],
    },
    "Retail & Consumer": {
        "Large Cap": [
            {
                "domain": "amazon.com",
                "name": "Amazon.com Inc.",
                "symbol": "AMZN",
                "cik": "1018724",
            },
            {
                "domain": "walmart.com",
                "name": "Walmart Inc.",
                "symbol": "WMT",
                "cik": "104169",
            },
            {
                "domain": "target.com",
                "name": "Target Corporation",
                "symbol": "TGT",
                "cik": "27419",
            },
            {
                "domain": "costco.com",
                "name": "Costco Wholesale",
                "symbol": "COST",
                "cik": "909832",
            },
            {
                "domain": "homedepot.com",
                "name": "The Home Depot",
                "symbol": "HD",
                "cik": "354950",
            },
            {
                "domain": "nike.com",
                "name": "NIKE Inc.",
                "symbol": "NKE",
                "cik": "320187",
            },
        ],
        "Mid Cap": [
            {
                "domain": "etsy.com",
                "name": "Etsy Inc.",
                "symbol": "ETSY",
                "cik": "1370637",
            },
            {
                "domain": "wayfair.com",
                "name": "Wayfair Inc.",
                "symbol": "W",
                "cik": "1616707",
            },
            {
                "domain": "williams-sonoma.com",
                "name": "Williams-Sonoma",
                "symbol": "WSM",
                "cik": "719955",
            },
            {
                "domain": "traderjoes.com",
                "name": "Trader Joe's",
                "symbol": "TJX",
                "cik": "109198",
            },
            {
                "domain": "chewy.com",
                "name": "Chewy Inc.",
                "symbol": "CHWY",
                "cik": "1766502",
            },
        ],
    },
    "Financial": {
        "Large Cap": [
            {
                "domain": "jpmorgan.com",
                "name": "JPMorgan Chase & Co.",
                "symbol": "JPM",
                "cik": "19617",
            },
            {
                "domain": "blackrock.com",
                "name": "BlackRock Inc.",
                "symbol": "BLK",
                "cik": "1364742",
            },
            {
                "domain": "visa.com",
                "name": "Visa Inc.",
                "symbol": "V",
                "cik": "1403161",
            },
            {
                "domain": "mastercard.com",
                "name": "Mastercard Inc.",
                "symbol": "MA",
                "cik": "1141391",
            },
            {
                "domain": "goldmansachs.com",
                "name": "Goldman Sachs Group",
                "symbol": "GS",
                "cik": "886982",
            },
            {
                "domain": "ml.com",
                "name": "Bank of America",
                "symbol": "BAC",
                "cik": "70858",
            },
        ],
        "Mid Cap": [
            {
                "domain": "coinbase.com",
                "name": "Coinbase Global Inc.",
                "symbol": "COIN",
                "cik": "1679788",
            },
            {
                "domain": "sofi.com",
                "name": "SoFi Technologies",
                "symbol": "SOFI",
                "cik": "1818874",
            },
            {
                "domain": "robinhood.com",
                "name": "Robinhood Markets",
                "symbol": "HOOD",
                "cik": "1783879",
            },
            {
                "domain": "square.com",
                "name": "Block Inc.",
                "symbol": "SQ",
                "cik": "1512673",
            },
            {
                "domain": "affirm.com",
                "name": "Affirm Holdings",
                "symbol": "AFRM",
                "cik": "1822250",
            },
        ],
    },
    "Healthcare": {
        "Large Cap": [
            {
                "domain": "pfizer.com",
                "name": "Pfizer Inc.",
                "symbol": "PFE",
                "cik": "78003",
            },
            {
                "domain": "unitedhealth.com",
                "name": "UnitedHealth Group",
                "symbol": "UNH",
                "cik": "731766",
            },
            {
                "domain": "jnj.com",
                "name": "Johnson & Johnson",
                "symbol": "JNJ",
                "cik": "200406",
            },
            {
                "domain": "abbvie.com",
                "name": "AbbVie Inc.",
                "symbol": "ABBV",
                "cik": "1551152",
            },
            {
                "domain": "merck.com",
                "name": "Merck & Co.",
                "symbol": "MRK",
                "cik": "310158",
            },
            {
                "domain": "lilly.com",
                "name": "Eli Lilly",
                "symbol": "LLY",
                "cik": "59478",
            },
        ],
        "Mid Cap": [
            {
                "domain": "modernatx.com",
                "name": "Moderna Inc.",
                "symbol": "MRNA",
                "cik": "1682852",
            },
            {
                "domain": "teladochealth.com",
                "name": "Teladoc Health",
                "symbol": "TDOC",
                "cik": "1477449",
            },
            {
                "domain": "edwards.com",
                "name": "Edwards Lifesciences",
                "symbol": "EW",
                "cik": "1099800",
            },
            {
                "domain": "illumina.com",
                "name": "Illumina Inc.",
                "symbol": "ILMN",
                "cik": "1110803",
            },
            {
                "domain": "biogen.com",
                "name": "Biogen Inc.",
                "symbol": "BIIB",
                "cik": "875045",
            },
        ],
    },
    "Industrial & Manufacturing": {
        "Large Cap": [
            {
                "domain": "ge.com",
                "name": "General Electric Company",
                "symbol": "GE",
                "cik": "40545",
            },
            {
                "domain": "caterpillar.com",
                "name": "Caterpillar Inc.",
                "symbol": "CAT",
                "cik": "18230",
            },
            {
                "domain": "3m.com",
                "name": "3M Company",
                "symbol": "MMM",
                "cik": "66740",
            },
            {
                "domain": "honeywell.com",
                "name": "Honeywell International",
                "symbol": "HON",
                "cik": "773840",
            },
            {
                "domain": "boeing.com",
                "name": "Boeing Company",
                "symbol": "BA",
                "cik": "12927",
            },
        ],
        "Mid Cap": [
            {
                "domain": "rockwellautomation.com",
                "name": "Rockwell Automation",
                "symbol": "ROK",
                "cik": "1024478",
            },
            {
                "domain": "northropgrumman.com",
                "name": "Northrop Grumman",
                "symbol": "NOC",
                "cik": "1133421",
            },
            {
                "domain": "paccar.com",
                "name": "PACCAR Inc.",
                "symbol": "PCAR",
                "cik": "75362",
            },
            {
                "domain": "emerson.com",
                "name": "Emerson Electric",
                "symbol": "EMR",
                "cik": "32604",
            },
        ],
    },
    "Energy": {
        "Large Cap": [
            {
                "domain": "chevron.com",
                "name": "Chevron Corporation",
                "symbol": "CVX",
                "cik": "93410",
            },
            {
                "domain": "exxonmobil.com",
                "name": "Exxon Mobil Corporation",
                "symbol": "XOM",
                "cik": "34088",
            },
            {
                "domain": "conocophillips.com",
                "name": "ConocoPhillips",
                "symbol": "COP",
                "cik": "1163165",
            },
            {
                "domain": "slb.com",
                "name": "Schlumberger",
                "symbol": "SLB",
                "cik": "87347",
            },
        ],
        "Mid Cap": [
            {
                "domain": "enphase.com",
                "name": "Enphase Energy",
                "symbol": "ENPH",
                "cik": "1463101",
            },
            {
                "domain": "plug.com",
                "name": "Plug Power Inc.",
                "symbol": "PLUG",
                "cik": "1093691",
            },
            {
                "domain": "sunrun.com",
                "name": "Sunrun Inc.",
                "symbol": "RUN",
                "cik": "1469367",
            },
            {
                "domain": "firstsolar.com",
                "name": "First Solar Inc.",
                "symbol": "FSLR",
                "cik": "1274494",
            },
        ],
    },
    "Media & Entertainment": {
        "Large Cap": [
            {
                "domain": "netflix.com",
                "name": "Netflix Inc.",
                "symbol": "NFLX",
                "cik": "1065280",
            },
            {
                "domain": "disney.com",
                "name": "The Walt Disney Company",
                "symbol": "DIS",
                "cik": "1744489",
            },
            {
                "domain": "meta.com",
                "name": "Meta Platforms Inc.",
                "symbol": "META",
                "cik": "1326801",
            },
            {
                "domain": "alphabet.com",
                "name": "Alphabet Inc.",
                "symbol": "GOOGL",
                "cik": "1652044",
            },
            {
                "domain": "comcast.com",
                "name": "Comcast Corporation",
                "symbol": "CMCSA",
                "cik": "1166691",
            },
        ],
        "Mid Cap": [
            {
                "domain": "spotify.com",
                "name": "Spotify Technology",
                "symbol": "SPOT",
                "cik": "1639920",
            },
            {
                "domain": "roku.com",
                "name": "Roku Inc.",
                "symbol": "ROKU",
                "cik": "1428439",
            },
            {
                "domain": "take2games.com",
                "name": "Take-Two Interactive",
                "symbol": "TTWO",
                "cik": "946581",
            },
            {
                "domain": "ea.com",
                "name": "Electronic Arts",
                "symbol": "EA",
                "cik": "712515",
            },
            {
                "domain": "warnerbros.com",
                "name": "Warner Bros Discovery",
                "symbol": "WBD",
                "cik": "1437107",
            },
        ],
    },
}


def get_all_companies() -> List[Dict]:
    """Get flat list of all companies."""
    companies = []
    for sector, cap_levels in COMPANIES.items():
        for cap_level, company_list in cap_levels.items():
            for company in company_list:
                companies.append({**company, "sector": sector, "cap_level": cap_level})
    return companies


def get_company_by_symbol(symbol: str) -> Dict:
    """Get company info by symbol."""
    for sector in COMPANIES.values():
        for cap in sector.values():
            for company in cap:
                if company["symbol"] == symbol:
                    # Ensure CIK is padded to 10 digits
                    company["cik"] = str(company["cik"]).zfill(10)
                    return company
    return None


def get_symbols() -> List[str]:
    """Get list of all company symbols."""
    return [company["symbol"] for company in get_all_companies()]


def get_companies_by_sector(sector: str) -> List[Dict]:
    """Get all companies in a sector."""
    return [company for company in get_all_companies() if company["sector"] == sector]
